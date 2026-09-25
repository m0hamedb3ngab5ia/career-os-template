"""Deterministic QA checks for a job directory.

Usage:
    python -m careeros.qa <job_dir> [--root <repo_root>] [--strict]

Prints the JSON report and exits 0 (report mode; callers gate on `pass`). With --strict it exits 1
when any hard check fails, for shell pipelines that gate on the exit status.

Importable:
    from careeros.qa import run_deterministic
    result = run_deterministic("data/jobs/<id>")

Output schema (dict / JSON):
    {
      "job_dir": str,
      "pass": bool,                      # no hard check failed
      "artifacts": {name: bool},         # which files were present
      "checks": [ {check, level: hard|soft, ok: bool, detail: str, skipped?: bool} ],
      "summary": {"hard_fail": int, "soft_fail": int, "skipped": int},
      "keyword_coverage": float | None,
      "cover_letter_word_count": int | None,   # computed from the body; frontmatter word_count is ignored
      "orphan_numbers": [...], "unknown_tools": [...], "banned_hits": [...],
      "confidential_hits": [...],        # "<file>: term '<t>'" | "<file>: patterns[<i>]"
      "bullet_shape": [ {id: str | None, line: str, issues: [weak_opener|no_metric|too_long]} ]
                                         # soft: resume.txt bullets that break _shared/resume_writing_rules.md
      # hard check `estimate_marked`: a number marked "~" in an `estimate: true` bullet keeps its "~" (or, in prose,
      #   about/approximately/roughly/around) wherever an artifact citing that bullet shows it
      # hard check `example_identity`: the example candidate's name/email in resume.txt or cover_letter.md
    }

A check that cannot run because its input artifact is missing is reported with
ok=True and skipped=True so that a partially prepared job dir never crashes the gate;
the `artifacts` map tells the caller what is missing.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

NUM_RE = re.compile(r"\$?\d[\d,\.]*[%KkMx+]?")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#\./-]*")
EM_DASH = "—"
PLACEHOLDER_RE = re.compile(r"\[(FILL IN|OPEN\b)", re.I)

# Capitalised tokens that are never "tools" (section headers, months, grammar words, generic geography).
TOOL_ALLOWLIST = {
    "i", "a", "an", "the", "and", "or", "of", "for", "with", "in", "on", "at", "to", "by", "from",
    "as", "is", "are", "was", "were", "be", "via", "per", "across", "into", "using", "vs",
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "january", "february", "march", "april", "june", "july", "august", "september", "october",
    "november", "december", "present", "current", "expected",
    "summary", "experience", "projects", "project", "education", "skills", "technical",
    "leadership", "languages", "frameworks", "tools", "concepts", "programming", "coursework",
    "relevant", "activities", "certifications", "awards", "honors", "interests", "libraries", "platforms",
    "gpa", "b.e", "b.e.", "b.s", "b.s.", "bs", "be", "bachelor", "bachelors", "bachelor's",
    "master", "masters", "degree", "university", "institute", "college", "school",
    "us", "usa", "u.s", "u.s.", "nj", "ny", "ct", "ma", "pa", "remote", "hybrid",
    "linkedin", "github", "email", "phone", "portfolio", "website",
    "inc", "llc", "co", "ltd", "corp", "group",
    "engineer", "engineering", "software", "developer", "intern", "internship", "co-op", "assistant",
    "research", "founder", "chair", "team", "member", "volunteer", "organizer", "instructor",
    "api", "apis", "ui", "ux", "cli", "crud", "etl", "elt", "ci/cd", "sdk", "ide", "os", "ios",
    "ai", "ml", "llm", "llms", "loc", "prs", "pr", "qa", "sql", "json", "yaml", "http", "https",
    "rest", "grpc", "tdd", "oop", "mvp", "beta", "testflight", "app", "store",
    "north", "south", "east", "west", "new", "city",
}
# bullet_shape defaults (config/qa.yaml: resume.soft.{weak_openers, bullet_max_words, scale_words} override them;
# a personal qa.yaml written before these keys existed gets these values).
DEFAULT_WEAK_OPENERS = ("worked on", "helped", "responsible for", "assisted", "participated in", "involved in",
                        "tasked with")
DEFAULT_BULLET_MAX_WORDS = 35
DEFAULT_SCALE_WORDS = ("users", "requests", "records", "teams", "services", "daily", "million", "thousand", "dozen")

# A candidate estimate ("~40%" in an `estimate: true` bullet) must stay hedged. Résumé bullets keep the "~";
# prose (cover letter, answers) may also say it in words.
ESTIMATE_RE = re.compile(r"~\s*(\$?\d[\d,\.]*[%KkMx+]?)")
HEDGE_WORDS = ("about", "approximately", "roughly", "around")

# Place names are not hardcoded: every word of the profile's identity.location and each experience /
# project / education `location` is allowed at runtime (ProfileIndex.place_words).


def _read_text(p: Path) -> str | None:
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8", errors="replace")


def _read_json(p: Path) -> Any:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:  # pragma: no cover - reported as a check
        return {"__parse_error__": str(e)}


def _load_yaml(p: Path) -> Any:
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def find_root(start: Path) -> Path:
    """Repo root = nearest ancestor containing config/pipeline.yaml. Falls back to careeros.config."""
    for p in (start.resolve(), *start.resolve().parents):
        if (p / "config" / "pipeline.yaml").exists():
            return p
    try:  # pragma: no cover
        from careeros.config import find_repo_root  # type: ignore

        return find_repo_root()
    except Exception:  # pragma: no cover
        return Path(__file__).resolve().parents[2]


def split_frontmatter(md: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter dict, body). Missing/invalid frontmatter -> ({}, md)."""
    if not md.startswith("---"):
        return {}, md
    parts = md.split("\n---", 1)
    if len(parts) < 2:
        return {}, md
    head = parts[0][3:]
    body = parts[1]
    if body.startswith("-"):  # '----' style edge
        body = body.lstrip("-")
    try:
        fm = yaml.safe_load(head) or {}
    except yaml.YAMLError:
        return {}, md
    if not isinstance(fm, dict):
        return {}, md
    return fm, body.lstrip("\n")


def number_tokens(text: str) -> set[str]:
    out = set()
    for m in NUM_RE.finditer(text or ""):
        tok = m.group(0).rstrip(".,").lower()
        if tok:
            out.add(tok)
    return out


def _term_in_text(term: str, text: str) -> bool:
    """Whole-term, case-insensitive match. "go" must not hit "governance"; "C++" / "Next.js" are
    matched literally with lookarounds on non-word characters instead of \\b (which fails after '+')."""
    pat = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
    return re.search(pat, text, re.IGNORECASE) is not None


def _count_words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


_FID_TOKEN = re.compile(r"[a-z0-9$%+#]+(?:[.'/-][a-z0-9$%+#]+)*")


def _fid_words(text: str) -> list[str]:
    return _FID_TOKEN.findall(str(text or "").lower())


def bullet_text_allowed(out: str, sources: Iterable[str]) -> bool:
    """tailor-resume rule 1: text is a source (master text or a declared variant) verbatim, optionally with
    a trailing clause trimmed: its words are a prefix of the source's words (punctuation ignored). A
    different leading verb must be declared as a variant in master.yaml."""
    ow = _fid_words(out)
    if len(ow) < 2:
        return False
    return any(_fid_words(src)[:len(ow)] == ow for src in sources)


def bullet_shape_issues(text: str, weak_openers: Iterable[str], max_words: int,
                        scale_words: Iterable[str] = DEFAULT_SCALE_WORDS) -> list[str]:
    """Soft résumé-bullet checks from .claude/skills/_shared/resume_writing_rules.md, in this order:
    `weak_opener` (starts with one of `weak_openers`, whole words, any case), `no_metric` (no digit and no
    scale word), `too_long` (more than `max_words` words)."""
    t = str(text or "").strip()
    low = t.lower()
    issues = []
    if any(re.match(re.escape(str(w).strip().lower()) + r"(?![a-z0-9])", low) for w in weak_openers if str(w).strip()):
        issues.append("weak_opener")
    if not re.search(r"\d", t) and not any(_term_in_text(str(w).strip(), t) for w in scale_words if str(w).strip()):
        issues.append("no_metric")
    if _count_words(t) > max_words:
        issues.append("too_long")
    return issues


def _standard_hit(question: str, path: Path, patterns: list[tuple[str, list[re.Pattern[str]]]]) -> str | None:
    """Key of the standard answer this question maps to. Uses the applier's matcher (EEO excluded,
    legal/salary wording guarded) so QA and the form filler agree; plain first-hit fallback otherwise."""
    try:
        from careeros.apply.questions import match_standard_answer
    except ImportError:  # pragma: no cover - applier not installed
        return next((k for k, rxs in patterns if any(rx.search(question) for rx in rxs)), None)
    hit = match_standard_answer(question, path)
    return hit[0] if hit else None


def _year(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v)
    m = re.match(r"(\d{4})", s)
    return m.group(1) if m else None


# --------------------------------------------------------------------------- #
# profile index
# --------------------------------------------------------------------------- #


class ProfileIndex:
    """Index of the master profile: bullet id -> record, plus allowed vocab."""

    def __init__(self, profile: dict[str, Any]):
        self.profile = profile or {}
        self.bullets: dict[str, dict[str, Any]] = {}
        self.bullet_parent: dict[str, dict[str, Any]] = {}
        self.narratives: dict[str, dict[str, Any]] = {}
        self.parents: dict[str, dict[str, Any]] = {}
        for section in ("experience", "projects", "leadership"):
            for entry in self.profile.get(section, []) or []:
                if not isinstance(entry, dict):
                    continue
                if entry.get("id"):
                    self.parents[entry["id"]] = entry
                for b in entry.get("bullets", []) or []:
                    if isinstance(b, dict) and b.get("id"):
                        self.bullets[b["id"]] = b
                        self.bullet_parent[b["id"]] = entry
        for n in self.profile.get("narratives", []) or []:
            if isinstance(n, dict) and n.get("id"):
                self.narratives[n["id"]] = n

    # ---- existence -------------------------------------------------------
    def exists(self, bid: str) -> bool:
        return bid in self.bullets or bid in self.narratives or bid in self.parents or bid in self.education_ids()

    def is_placeholder(self, bid: str) -> bool:
        b = self.bullets.get(bid)
        if b is None:
            return False
        if b.get("placeholder"):
            return True
        # "[FILL IN ...]" and "[OPEN: ...]" are the two placeholder spellings used in master.yaml
        return PLACEHOLDER_RE.search(str(b.get("text", ""))) is not None

    def education_ids(self) -> set[str]:
        return {e.get("id") for e in self.profile.get("education", []) or [] if isinstance(e, dict) and e.get("id")}

    # ---- text pools ------------------------------------------------------
    def identity_text(self) -> str:
        ident = self.profile.get("identity", {}) or {}
        return " ".join(str(v) for v in ident.values() if v)

    def education_text(self) -> str:
        parts = []
        for e in self.profile.get("education", []) or []:
            if not isinstance(e, dict):
                continue
            for k in ("school", "degree", "gpa", "location", "start", "end"):
                if e.get(k) is not None:
                    parts.append(str(e[k]))
            for k in ("coursework", "activities"):
                parts.extend(str(x) for x in e.get(k, []) or [])
        return " ".join(parts)

    def header_text(self) -> str:
        """Company/title/team/location/name/dates for every experience/project/leadership entry."""
        parts = []
        for section in ("experience", "projects", "leadership"):
            for e in self.profile.get(section, []) or []:
                if not isinstance(e, dict):
                    continue
                for k in ("company", "title", "team", "location", "name", "org", "role", "date", "start", "end"):
                    if e.get(k) is not None:
                        parts.append(str(e[k]))
                    y = _year(e.get(k)) if k in ("date", "start", "end") else None
                    if y:
                        parts.append(y)
        return " ".join(parts)

    def place_words(self) -> set[str]:
        """Lower-cased words of identity.location and every experience/project/education `location`."""
        locs = [str((self.profile.get("identity", {}) or {}).get("location") or "")]
        for section in ("experience", "projects", "education", "leadership"):
            for e in self.profile.get(section, []) or []:
                if isinstance(e, dict) and e.get("location"):
                    locs.append(str(e["location"]))
        return {w.rstrip(".,;:").lower() for w in WORD_RE.findall(" ".join(locs))}

    def summary_text(self) -> str:
        return " ".join(str(v) for v in (self.profile.get("summary_variants", {}) or {}).values())

    def skills_text(self) -> str:
        sk = self.profile.get("skills", {}) or {}
        return " ".join(str(x) for vals in sk.values() for x in (vals or []))

    def stacks_text(self) -> str:
        parts = []
        for section in ("experience", "projects"):
            for e in self.profile.get(section, []) or []:
                if isinstance(e, dict):
                    parts.extend(str(x) for x in e.get("stack", []) or [])
        return " ".join(parts)

    def bullet_sources(self, bid: str) -> list[str]:
        """The bullet's master text and each declared variant, separately."""
        b = self.bullets.get(bid)
        if not b:
            return []
        variants = b.get("variants") or []
        vals = variants.values() if isinstance(variants, dict) else variants
        return [str(b.get("text", ""))] + [str(v) for v in vals]

    def bullet_text(self, bid: str) -> str:
        b = self.bullets.get(bid)
        if b:
            t = str(b.get("text", ""))
            variants = b.get("variants") or []
            # master.yaml stores variants as a mapping ({short: "..."}); older data may use a list
            for v in (variants.values() if isinstance(variants, dict) else variants):
                t += " " + str(v)
            return t
        n = self.narratives.get(bid)
        if n:
            return str(n.get("text", ""))
        return ""


# --------------------------------------------------------------------------- #
# id extraction from artifacts
# --------------------------------------------------------------------------- #


def collect_ids(obj: Any) -> set[str]:
    """Collect bullet/narrative ids from a resume.json-like structure.

    Recognises: any list under a key ending in `_ids` or named `bullet_ids`/`narrative_ids`,
    dicts inside a `bullets` list with an `id`, and top-level `bullet_ids`.
    """
    found: set[str] = set()

    def walk(o: Any, key: str | None = None) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("bullet_ids", "narrative_ids", "ids") or k.endswith("_ids"):
                    if isinstance(v, list):
                        found.update(str(x) for x in v if isinstance(x, (str, int)))
                elif k == "bullets" and isinstance(v, list):
                    for b in v:
                        if isinstance(b, dict) and b.get("id"):
                            found.add(str(b["id"]))
                        elif isinstance(b, str):
                            found.add(b)
                else:
                    walk(v, k)
        elif isinstance(o, list):
            for x in o:
                walk(x, key)

    walk(obj)
    return found


def cited_ids_cover_letter(fm: dict[str, Any]) -> set[str]:
    ids = set()
    for k in ("bullet_ids_used", "narrative_ids_used", "bullet_ids", "narrative_ids"):
        v = fm.get(k)
        if isinstance(v, list):
            ids.update(str(x) for x in v)
    return ids


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #


class Checker:
    def __init__(self, job_dir: Path, root: Path):
        self.job_dir = job_dir
        self.root = root
        self.qa_cfg = _load_yaml(root / "config" / "qa.yaml")
        pipeline = _load_yaml(root / "config" / "pipeline.yaml")
        paths = (pipeline.get("paths") or {}) if isinstance(pipeline, dict) else {}
        prof_path = Path(paths.get("profile", "profile/master.yaml"))
        if not prof_path.is_absolute():
            prof_path = root / prof_path
        self.profile = ProfileIndex(_load_yaml(prof_path))
        self.prof_path = prof_path
        # profile/confidential_terms.yaml sits next to master.yaml (gitignored with the rest of profile/)
        self.confidential_path = prof_path.parent / "confidential_terms.yaml"
        sa_path = Path(paths.get("standard_answers", prof_path.parent / "standard_answers.yaml"))
        self.standard_answers_path = sa_path if sa_path.is_absolute() else root / sa_path
        self.checks: list[dict[str, Any]] = []
        self.extras: dict[str, Any] = {"orphan_numbers": [], "unknown_tools": [], "banned_hits": []}

        # artifacts
        self.posting = _read_json(job_dir / "posting.json")
        self.score = _read_json(job_dir / "score.json")
        self.resume_json = _read_json(job_dir / "resume.json")
        self.resume_txt = _read_text(job_dir / "resume.txt")
        self.cover_md = _read_text(job_dir / "cover_letter.md")
        self.answers = _read_json(job_dir / "answers.json")
        self.answers_raw = _read_text(job_dir / "answers.json")
        self.outreach_raw = _read_text(job_dir / "outreach.json")
        self.pdf_path = job_dir / "resume.pdf"
        self.artifacts = {
            "posting.json": self.posting is not None,
            "score.json": self.score is not None,
            "resume.json": self.resume_json is not None,
            "resume.txt": self.resume_txt is not None,
            "cover_letter.md": self.cover_md is not None,
            "answers.json": self.answers is not None,
            "resume.pdf": self.pdf_path.exists(),
        }
        if self.cover_md is not None:
            self.cover_fm, self.cover_body = split_frontmatter(self.cover_md)
        else:
            self.cover_fm, self.cover_body = {}, ""

    # ---- recording -------------------------------------------------------
    def add(self, check: str, level: str, ok: bool, detail: str, skipped: bool = False) -> None:
        rec = {"check": check, "level": level, "ok": bool(ok), "detail": detail}
        if skipped:
            rec["skipped"] = True
        self.checks.append(rec)

    def skip(self, check: str, level: str, why: str) -> None:
        self.add(check, level, True, f"skipped: {why}", skipped=True)

    # ---- individual checks ----------------------------------------------
    def check_artifacts(self) -> None:
        req = [k for k in ("resume.json", "resume.txt") if not self.artifacts.get(k)]
        # tailor-resume writes both before any QA run; a dir without them has nothing to gate
        self.add("resume_present", "hard", not req, "resume.json + resume.txt present" if not req
                 else f"missing: {', '.join(req)}")
        missing = [k for k, v in self.artifacts.items() if not v and k != "resume.pdf"]
        self.add("artifacts_present", "soft", not missing,
                 "all artifacts present" if not missing else f"missing: {', '.join(missing)}")
        for name, obj in (("posting.json", self.posting), ("score.json", self.score),
                          ("resume.json", self.resume_json), ("answers.json", self.answers)):
            if isinstance(obj, dict) and "__parse_error__" in obj:
                self.add(f"json_valid:{name}", "hard", False, obj["__parse_error__"])

    def check_banned(self) -> None:
        banned = [str(b).strip() for b in self.qa_cfg.get("banned_phrases", []) or []]
        docs: dict[str, str] = {}
        if self.cover_md is not None:
            docs["cover_letter.md"] = self.cover_body
        if self.resume_txt is not None:
            docs["resume.txt"] = self.resume_txt
        if isinstance(self.answers, list):
            docs["answers.json"] = " \n".join(str(a.get("answer") or "") for a in self.answers if isinstance(a, dict))
        if not docs:
            self.skip("banned_phrases", "hard", "no text artifacts")
            return
        hits = []
        for name, text in docs.items():
            low = text.lower()
            for phrase in banned:
                p = phrase.lower()
                # "dear hiring manager," -> also catch without trailing comma
                pat = r"(?<![a-z])" + re.escape(p.rstrip(",")) + r"(?![a-z])"
                if re.search(pat, low):
                    hits.append({"file": name, "phrase": phrase})
        self.extras["banned_hits"] = hits
        self.add("banned_phrases", "hard", not hits,
                 "none found" if not hits else "; ".join(f"{h['file']}: '{h['phrase']}'" for h in hits))

    def check_confidential(self) -> None:
        """Hard fail when a term/pattern from profile/confidential_terms.yaml appears in any artifact.

        File shape: {employer: str (informational), terms: [str] (case-insensitive, whole word),
        patterns: [regex] (as written)}. Missing file -> skipped. Unreadable file -> hard fail (fail closed).
        """
        name = "confidential_terms"
        if not self.confidential_path.exists():
            self.skip(name, "hard", f"no {self.confidential_path.name}")
            return
        try:
            cfg = _load_yaml(self.confidential_path)
        except yaml.YAMLError as e:
            self.add(name, "hard", False, f"cannot parse {self.confidential_path.name}: {str(e).splitlines()[0]}")
            return
        cfg = cfg if isinstance(cfg, dict) else {}
        terms = [str(t).strip() for t in cfg.get("terms") or [] if str(t).strip()]
        patterns: list[tuple[int, re.Pattern[str]]] = []
        for i, pat in enumerate(cfg.get("patterns") or []):
            try:
                patterns.append((i, re.compile(str(pat))))
            except re.error as e:
                self.add(name, "hard", False, f"patterns[{i}] is not a valid regex: {e}")
                return
        docs = {"resume.txt": self.resume_txt, "cover_letter.md": self.cover_md,
                "answers.json": self.answers_raw, "outreach.json": self.outreach_raw,
                "resume.pdf": self._pdf_text() if self.pdf_path.exists() else None}  # the uploaded file
        docs = {k: v for k, v in docs.items() if v is not None}
        if not docs:
            self.skip(name, "hard", "no text artifacts")
            return
        hits: list[str] = []
        for fname, text in docs.items():
            hits += [f"{fname}: term '{t}'" for t in terms if _term_in_text(t, text)]
            # pattern matches may be account numbers or hostnames: report the rule, never the match
            hits += [f"{fname}: patterns[{i}]" for i, rx in patterns if rx.search(text)]
        self.extras["confidential_hits"] = hits
        self.add(name, "hard", not hits,
                 f"{len(terms)} terms, {len(patterns)} patterns; none found in {', '.join(docs)}" if not hits
                 else "confidential content: " + "; ".join(hits))

    def check_example_identity(self) -> None:
        """Hard fail when resume.txt or cover_letter.md carries the fictional example candidate's name or
        email (examples/profile/master.yaml): an untouched `careeros init` copy must never reach an
        application. Skipped when the QA root is the shipped examples/ repo itself (tests, demos)."""
        from careeros.doctor import example_identity, find_examples

        name = "example_identity"
        examples = find_examples(self.root)
        if examples is None:
            self.skip(name, "hard", "no examples/ to compare against")
            return
        if self.prof_path.resolve().is_relative_to(examples.resolve()):
            self.skip(name, "hard", "QA root is the shipped example repo")
            return
        ident = example_identity(examples)
        needles = [v for v in (ident.get("name"), ident.get("email")) if v]
        docs = {"resume.txt": self.resume_txt, "cover_letter.md": self.cover_md}
        docs = {k: v for k, v in docs.items() if v is not None}
        if not docs:
            self.skip(name, "hard", "no resume.txt or cover_letter.md")
            return
        hits = [f"{fname}: '{v}'" for fname, text in docs.items() for v in needles if v.lower() in text.lower()]
        self.add(name, "hard", not hits,
                 "no example identity" if not hits else
                 "example candidate data (fill in profile/master.yaml, run `careeros doctor`): " + "; ".join(hits))

    def check_word_counts(self) -> None:
        cl_cfg = self.qa_cfg.get("cover_letter", {}) or {}
        if self.cover_md is not None:
            n = _count_words(self.cover_body)
            lo, hi = int(cl_cfg.get("min_words", 120)), int(cl_cfg.get("max_words", 250))
            # word_count is computed here from the body; frontmatter word_count is informational only.
            self.extras["cover_letter_word_count"] = n
            self.add("cover_letter_word_count", "hard", lo <= n <= hi, f"{n} words (limit {lo}-{hi})")
        else:
            self.skip("cover_letter_word_count", "hard", "cover_letter.md missing")
        if self.resume_txt is not None:
            n = _count_words(self.resume_txt)
            # measured on templates/resume/default.tex: 1 page up to ~570 words / 18 bullets; 2 pages from ~600
            self.add("resume_word_budget", "soft", n <= 600, f"{n} words (budget ~550, ceiling 600; pdf_page_count is the real gate)")
        else:
            self.skip("resume_word_budget", "soft", "resume.txt missing")
        if isinstance(self.answers, list):
            over = []
            for i, a in enumerate(self.answers):
                if not isinstance(a, dict):
                    continue
                lim = a.get("char_limit")
                ans = a.get("answer")
                if lim and ans and len(str(ans)) > int(lim):
                    over.append(f"#{i} {len(str(ans))}>{lim}")
            self.add("answers_within_char_limit", "hard", not over,
                     "all within limits" if not over else ", ".join(over))

    def check_em_dashes(self) -> None:
        rules = self.qa_cfg.get("style_rules", []) or []
        max_em = 2
        for r in rules:
            if isinstance(r, dict) and "max_em_dashes_per_doc" in r:
                max_em = int(r["max_em_dashes_per_doc"])
        any_doc = False
        for name, text in (("cover_letter.md", self.cover_body if self.cover_md is not None else None),
                           ("resume.txt", self.resume_txt)):
            if text is None:
                continue
            any_doc = True
            n = text.count(EM_DASH)
            self.add(f"em_dashes:{name}", "soft", n <= max_em, f"{n} em-dashes (max {max_em})")
        if isinstance(self.answers, list):
            for i, a in enumerate(self.answers):
                if isinstance(a, dict) and a.get("answer"):
                    n = str(a["answer"]).count(EM_DASH)
                    if n > max_em:
                        self.add(f"em_dashes:answers.json#{i}", "soft", False, f"{n} em-dashes (max {max_em})")
            any_doc = True
        if not any_doc:
            self.skip("em_dashes", "soft", "no text artifacts")

    def _cited_ids(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        if isinstance(self.resume_json, dict) and "__parse_error__" not in self.resume_json:
            out["resume.json"] = collect_ids(self.resume_json)
        if self.cover_md is not None:
            out["cover_letter.md"] = cited_ids_cover_letter(self.cover_fm)
        if isinstance(self.answers, list):
            ids = set()
            for a in self.answers:
                if isinstance(a, dict):
                    ids.update(collect_ids({"bullet_ids": a.get("bullet_ids", [])}))
                    ids.update(collect_ids({"narrative_ids": a.get("narrative_ids", [])}))
            out["answers.json"] = ids
        return out

    def check_truth_trace(self) -> None:
        cited = self._cited_ids()
        if not cited:
            self.skip("truth_trace", "hard", "no artifacts cite ids")
            return
        problems = []
        for src, ids in cited.items():
            for bid in sorted(ids):
                if not self.profile.exists(bid):
                    problems.append(f"{src}: unknown id '{bid}'")
                elif self.profile.is_placeholder(bid):
                    problems.append(f"{src}: placeholder bullet '{bid}' used")
        total = sum(len(v) for v in cited.values())
        self.add("truth_trace", "hard", not problems,
                 f"{total} ids cited, all valid" if not problems else "; ".join(problems))
        if self.cover_md is not None and not cited.get("cover_letter.md"):
            self.add("cover_letter_cites_ids", "hard", False,
                     "cover_letter.md frontmatter has no bullet_ids_used / narrative_ids_used")

    def check_estimates(self) -> None:
        """Hard: bullet_fidelity and number_audit ignore "~", so an `estimate: true` bullet's "~40" shown as a bare
        "40" would pass both. Every occurrence of an estimated number in an artifact that cites the bullet must be
        hedged, unless another cited bullet states that same number exactly."""
        name = "estimate_marked"
        cited = self._cited_ids()
        docs: list[tuple[str, str, set[str], bool]] = []   # (file, text, cited ids, prose?)
        if self.resume_txt is not None:
            docs.append(("resume.txt", self.resume_txt, cited.get("resume.json", set()), False))
        if self.cover_md is not None:
            docs.append(("cover_letter.md", self.cover_body, cited.get("cover_letter.md", set()), True))
        if isinstance(self.answers, list):
            docs.append(("answers.json", "\n".join(str(a.get("answer") or "") for a in self.answers if isinstance(a, dict)),
                         cited.get("answers.json", set()), True))
        if not docs:
            self.skip(name, "hard", "no text artifacts")
            return
        problems, n_est = [], 0
        for fname, text, ids, prose in docs:
            est = [b for b in sorted(ids) if (self.profile.bullets.get(b) or {}).get("estimate") is True]
            if not est:
                continue
            exact = number_tokens(" ".join(ESTIMATE_RE.sub("", self.profile.bullet_text(b))
                                           for b in ids if b not in est))
            hedge = r"(?:~\s*" + ("|(?:" + "|".join(HEDGE_WORDS) + r")\s+" if prose else "") + r")$"
            for bid in est:
                for num in dict.fromkeys(m.rstrip(".,") for m in ESTIMATE_RE.findall(self.profile.bullet_text(bid))):
                    n_est += 1
                    if num.lower() in exact:
                        continue
                    for m in re.finditer(r"(?<![\d.,$])" + re.escape(num) + r"(?![\d])", text):
                        if not re.search(hedge, text[max(0, m.start() - 20):m.start()], re.I):
                            problems.append(f"{fname}: {bid} estimate {num} shown without ~")
                            break
        self.add(name, "hard", not problems,
                 (f"{n_est} estimated numbers keep their ~" if n_est else "no estimate bullets cited")
                 if not problems else "; ".join(problems) + " (profile marks it estimate: true; keep the ~)")

    def _allowed_numbers(self, ids: Iterable[str], extra_text: str = "") -> set[str]:
        pool = [self.profile.identity_text(), self.profile.education_text(), self.profile.header_text(), extra_text]
        for bid in ids:
            pool.append(self.profile.bullet_text(bid))
        return number_tokens(" ".join(pool))

    def check_numbers(self) -> None:
        cited = self._cited_ids()
        ran = False
        if self.resume_txt is not None:
            ran = True
            ids = cited.get("resume.json", set())
            extra = self.profile.skills_text() + " " + self.profile.summary_text()
            allowed = self._allowed_numbers(ids, extra)
            found = number_tokens(self.resume_txt)
            orphans = sorted(found - allowed)
            self.extras["orphan_numbers"].extend({"file": "resume.txt", "number": o} for o in orphans)
            self.add("number_audit:resume.txt", "hard", not orphans,
                     f"{len(found)} numbers, all traced" if not orphans else f"orphan numbers: {', '.join(orphans)}")
        if self.cover_md is not None:
            ran = True
            ids = cited.get("cover_letter.md", set())
            extra = ""
            # Company facts sourced from the posting are legitimate; allow numbers present in posting text.
            if isinstance(self.posting, dict):
                extra += " " + str(self.posting.get("description_text", "")) + " " + str(self.posting.get("title", ""))
                for k in ("salary_min", "salary_max"):
                    if self.posting.get(k) is not None:
                        extra += f" {self.posting[k]}"
            for f in (self.cover_fm.get("facts_used") or self.cover_fm.get("company_facts") or []):
                if isinstance(f, dict):
                    extra += " " + str(f.get("fact", ""))
            allowed = self._allowed_numbers(ids, extra + " " + self.profile.summary_text())
            found = number_tokens(self.cover_body)
            orphans = sorted(found - allowed)
            self.extras["orphan_numbers"].extend({"file": "cover_letter.md", "number": o} for o in orphans)
            self.add("number_audit:cover_letter.md", "hard", not orphans,
                     f"{len(found)} numbers, all traced" if not orphans else f"orphan numbers: {', '.join(orphans)}")
        if isinstance(self.answers, list):
            ran = True
            orph_all = []
            for i, a in enumerate(self.answers):
                if not isinstance(a, dict) or not a.get("answer") or a.get("type") == "standard":
                    continue
                ids = set(str(x) for x in (a.get("bullet_ids") or [])) | set(str(x) for x in (a.get("narrative_ids") or []))
                extra = str(self.posting.get("description_text", "")) if isinstance(self.posting, dict) else ""
                allowed = self._allowed_numbers(ids, extra + " " + self.profile.summary_text())
                orphans = sorted(number_tokens(str(a["answer"])) - allowed)
                if orphans:
                    orph_all.append(f"#{i}: {', '.join(orphans)}")
                    self.extras["orphan_numbers"].extend({"file": f"answers.json#{i}", "number": o} for o in orphans)
            self.add("number_audit:answers.json", "hard", not orph_all,
                     "all traced" if not orph_all else "; ".join(orph_all))
        if not ran:
            self.skip("number_audit", "hard", "no text artifacts")

    def _cap_tokens(self, text: str) -> list[str]:
        """Capitalised tokens that are not at sentence/line/bullet start."""
        out = []
        for line in text.splitlines():
            line = line.strip().lstrip("-•*·").strip()
            for sent in re.split(r"(?<=[.!?])\s+", line):
                words = WORD_RE.findall(sent)
                for w in words[1:]:
                    w = w.rstrip(".,;:").strip("/")
                    if len(w) >= 2 and w[0].isupper():
                        out.append(w)
        return out

    def check_tools(self) -> None:
        if self.resume_txt is None:
            self.skip("tool_audit", "hard", "resume.txt missing")
            return
        ids = self._cited_ids().get("resume.json", set())
        vocab_src = " ".join([
            self.profile.skills_text(), self.profile.stacks_text(), self.profile.identity_text(),
            self.profile.education_text(), self.profile.header_text(), self.profile.summary_text(),
            *[self.profile.bullet_text(b) for b in ids],
        ])
        vocab = {w.rstrip(".,;:").lower() for w in WORD_RE.findall(vocab_src)} | self.profile.place_words()
        # also allow each hyphen/slash part of vocab words (e.g. "CI/CD" -> "CI", "CD")
        for w in list(vocab):
            for part in re.split(r"[/\-]", w):
                if part:
                    vocab.add(part)
        unknown = []
        for tok in self._cap_tokens(self.resume_txt):
            low = tok.lower()
            if low in vocab or low in TOOL_ALLOWLIST:
                continue
            parts = [p for p in re.split(r"[/\-]", low) if p]
            if parts and all(p in vocab or p in TOOL_ALLOWLIST for p in parts):
                continue
            if tok not in unknown:
                unknown.append(tok)
        self.extras["unknown_tools"] = unknown
        self.add("tool_audit", "hard", not unknown,
                 "all capitalised terms traced to profile" if not unknown
                 else f"not in profile skills/cited bullets: {', '.join(unknown)}")

    def _resume_entries(self) -> list[dict[str, Any]]:
        rj = self.resume_json if isinstance(self.resume_json, dict) and "__parse_error__" not in self.resume_json else {}
        out = []
        for section in ("experience", "projects", "leadership"):
            out.extend(e for e in rj.get(section) or [] if isinstance(e, dict))
        return out

    def check_bullet_fidelity(self) -> None:
        """Each resume.json bullet's text is its master text / a variant (verb swap + trailing trim only);
        summary is a profile summary_variant verbatim or null."""
        rj = self.resume_json if isinstance(self.resume_json, dict) and "__parse_error__" not in self.resume_json else None
        if rj is None:
            self.skip("bullet_fidelity", "hard", "resume.json missing")
            return
        problems, n = [], 0
        for e in self._resume_entries():
            for b in e.get("bullets") or []:
                if not isinstance(b, dict) or not str(b.get("id") or "").strip():
                    problems.append(f"bullet without an id in '{e.get('id')}': {str(b)[:80]!r}")
                    continue
                if not str(b.get("text") or "").strip():
                    problems.append(f"'{b['id']}' has no text")
                    continue
                n += 1
                bid = str(b["id"])
                sources = self.profile.bullet_sources(bid)
                if sources and not bullet_text_allowed(str(b["text"]), sources):
                    problems.append(f"'{bid}' text differs from master text/variants: {str(b['text'])[:80]!r}")
        summary = rj.get("summary")
        if summary:
            variants = [str(v).strip() for v in (self.profile.profile.get("summary_variants") or {}).values()]
            if str(summary).strip() not in variants:
                problems.append("summary is not one of profile.summary_variants")
        self.add("bullet_fidelity", "hard", not problems,
                 f"{n} bullets match master text/variants" if not problems else "; ".join(problems))

    def check_entry_headers(self) -> None:
        """Every experience/project/leadership/education entry names a profile entry by `id`, and its
        company/title/team/name/school/degree/gpa/location equal that entry; dates keep the same year
        (display format may change), an open-ended profile role stays `Present`."""
        rj = self.resume_json if isinstance(self.resume_json, dict) and "__parse_error__" not in self.resume_json else None
        if rj is None:
            self.skip("entry_headers", "hard", "resume.json missing")
            return
        edu = {e.get("id"): e for e in self.profile.profile.get("education") or [] if isinstance(e, dict)}
        required = {"experience": ("company", "title", "start", "end"), "projects": ("name",),
                    "education": ("school", "degree")}
        fields = {"experience": ("company", "team", "location"), "projects": ("name",),
                  "leadership": ("org", "role", "name"), "education": ("school", "degree", "gpa", "location")}
        problems = []
        for section, keys in fields.items():
            for e in rj.get(section) or []:
                if not isinstance(e, dict):
                    continue
                eid = str(e.get("id") or "")
                src = edu.get(eid) if section == "education" else self.profile.parents.get(eid)
                if not src:
                    problems.append(f"{section}: entry {eid or '<no id>'} not in profile")
                    continue
                missing = [k for k in required.get(section, ()) if str(e.get(k) or "").strip() == ""]
                if missing:
                    problems.append(f"{eid}: missing {', '.join(missing)}")
                for k in keys:
                    if e.get(k) not in (None, "") and str(e[k]).strip() != str(src.get(k, "")).strip():
                        problems.append(f"{eid}.{k} {e[k]!r} != profile {src.get(k)!r}")
                if section == "experience" and e.get("title") not in (None, ""):
                    titles = {str(src.get(t)).strip() for t in ("title", "title_display") if src.get(t)}
                    if str(e["title"]).strip() not in titles:
                        problems.append(f"{eid}.title {e['title']!r} not in profile {sorted(titles)}")
                for k in ("start", "end", "date"):
                    out = e.get(k)
                    if out in (None, ""):
                        continue
                    want = src.get(k)
                    if k == "end" and (want is None or str(want).lower() in ("present", "current")):
                        if str(out).strip().lower() not in ("present", "current"):
                            problems.append(f"{eid}.end {out!r} but profile role is open-ended")
                    elif _year(want) and _year(re.sub(r"^\D*", "", str(out))) != _year(want):
                        problems.append(f"{eid}.{k} {out!r} != profile {want!r}")
        self.add("entry_headers", "hard", not problems,
                 "entry headers match profile" if not problems else "; ".join(problems))

    def check_skills_traced(self) -> None:
        rj = self.resume_json if isinstance(self.resume_json, dict) and "__parse_error__" not in self.resume_json else None
        skills = (rj or {}).get("skills")
        if not isinstance(skills, dict) or not any(skills.values()):
            self.skip("skills_traced", "hard", "resume.json has no skills")
            return
        allowed = {str(x).strip().lower() for vals in (self.profile.profile.get("skills") or {}).values()
                   for x in (vals or [])}
        for e in self._resume_entries():
            parent = self.profile.parents.get(str(e.get("id") or ""), {})
            allowed |= {str(x).strip().lower() for x in parent.get("stack") or []}
        cited = " ".join(self.profile.bullet_text(b) for b in self._cited_ids().get("resume.json", set()))
        unknown = [str(t) for vals in skills.values() for t in (vals or [])
                   if str(t).strip().lower() not in allowed and not _term_in_text(str(t).strip(), cited)]
        self.add("skills_traced", "hard", not unknown,
                 "all skills in profile skills/stack/cited bullets" if not unknown
                 else f"not in profile: {', '.join(unknown)}")

    def check_standard_answers(self) -> None:
        """type=standard answers equal profile/standard_answers.yaml verbatim (by standard_key; null stays
        null); sensitive / freeform-salary answers that are not standard are never filled."""
        if not isinstance(self.answers, list):
            self.skip("standard_answers", "hard", "answers.json missing")
            return
        try:
            sa = _load_yaml(self.standard_answers_path) if self.standard_answers_path.exists() else None
        except yaml.YAMLError as e:
            self.add("standard_answers", "hard", False, f"cannot parse {self.standard_answers_path.name}: {e}")
            return
        table: dict[str, Any] = {}
        patterns: list[tuple[str, list[re.Pattern[str]]]] = []  # file order: first hit wins (as the applier)
        if isinstance(sa, dict):
            for ent in sa.get("answers") or []:
                if isinstance(ent, dict) and ent.get("key"):
                    table[str(ent["key"])] = ent.get("answer")
                    rxs = []
                    for m in ent.get("match") or []:
                        try:
                            rxs.append(re.compile(str(m), re.I))
                        except re.error:
                            continue
                    patterns.append((str(ent["key"]), rxs))
            for k, ent in (sa.get("eeo") or {}).items():
                if isinstance(ent, dict):
                    table[f"eeo.{k}"] = ent.get("answer")
        def same(ans: Any, want: Any) -> bool:
            return ans in (None, "") if want is None else (ans is not None and str(ans).strip() == str(want).strip())

        problems = []
        for i, a in enumerate(self.answers):
            if not isinstance(a, dict):
                continue
            ans = a.get("answer")
            question = str(a.get("question") or "")
            hit = _standard_hit(question, self.standard_answers_path, patterns) if sa is not None else None
            if hit is not None:
                # the question's own pattern match decides the key, whatever type/standard_key the record says
                if not same(ans, table[hit]):
                    problems.append(f"#{i}: question matches standard '{hit}' but the answer differs")
                continue
            if a.get("type") == "standard":
                key = a.get("standard_key")
                if sa is None:
                    problems.append(f"#{i}: {self.standard_answers_path.name} missing")
                elif not key or str(key) not in table:
                    problems.append(f"#{i}: standard_key {key!r} not in {self.standard_answers_path.name}")
                else:
                    if not same(ans, table[str(key)]):
                        problems.append(f"#{i}: {key} answer differs from {self.standard_answers_path.name}")
            elif a.get("class") in ("sensitive", "salary_freeform") and ans not in (None, ""):
                problems.append(f"#{i}: {a.get('class')} answer must be left for the candidate (Action Item)")
        self.add("standard_answers", "hard", not problems,
                 "standard answers match profile" if not problems else "; ".join(problems))

    def _contact_fields(self) -> dict[str, str]:
        ident = self.profile.profile.get("identity", {}) or {}
        out = {}
        for k in ("name", "email", "phone", "linkedin", "github"):
            v = ident.get(k)
            if v:
                out[k] = str(v)
        return out

    def _contact_missing(self, text: str) -> list[str]:
        low = re.sub(r"\s+", "", text.lower())
        missing = []
        for k, v in self._contact_fields().items():
            needle = re.sub(r"\s+", "", v.lower())
            if k in ("linkedin", "github"):
                needle = needle.replace("https://", "").replace("http://", "").replace("www.", "")
            if k == "phone":
                digits = re.sub(r"\D", "", v)
                if digits not in re.sub(r"\D", "", text):
                    missing.append(k)
                continue
            if needle not in low:
                missing.append(k)
        return missing

    def check_contact(self) -> None:
        if self.resume_txt is None:
            self.skip("contact_intact:resume.txt", "hard", "resume.txt missing")
            return
        missing = self._contact_missing(self.resume_txt)
        self.add("contact_intact:resume.txt", "hard", not missing,
                 "name/email/phone/linkedin/github present" if not missing else f"missing: {', '.join(missing)}")

    def _pdf_text(self) -> str | None:
        """Extracted text of resume.pdf (None if pypdf is missing or the file is unreadable)."""
        try:
            from pypdf import PdfReader  # type: ignore

            return "\n".join((p.extract_text() or "") for p in PdfReader(str(self.pdf_path)).pages)
        except Exception:  # noqa: BLE001 - check_pdf reports unreadable PDFs
            return None

    def check_pdf(self) -> None:
        if not self.pdf_path.exists():
            self.skip("pdf", "hard", "resume.pdf not built")
            return
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError:  # pragma: no cover
            self.add("pdf", "soft", False, "pypdf not installed; cannot inspect resume.pdf")
            return
        try:
            reader = PdfReader(str(self.pdf_path))
            pages = len(reader.pages)
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as e:  # pragma: no cover
            self.add("pdf", "hard", False, f"cannot read resume.pdf: {e}")
            return
        max_pages = int((self.qa_cfg.get("resume", {}) or {}).get("max_pages", 1))
        self.add("pdf_page_count", "hard", pages <= max_pages, f"{pages} page(s) (max {max_pages})")
        missing = self._contact_missing(text)
        self.add("contact_intact:resume.pdf", "hard", not missing,
                 "contact fields survive extraction" if not missing else f"missing after extraction: {', '.join(missing)}")

    def check_keyword_coverage(self) -> None:
        if not isinstance(self.score, dict) or self.resume_txt is None:
            self.skip("keyword_coverage", "soft", "score.json or resume.txt missing")
            self.extras["keyword_coverage"] = None
            return
        req = [str(s) for s in (self.score.get("required_skills") or [])]
        if not req:
            self.skip("keyword_coverage", "soft", "score.json has no required_skills")
            self.extras["keyword_coverage"] = None
            return
        # Coverage is computed from resume.txt ONLY. Never resume.json (its meta.missing_terms /
        # keyword_mirror would make missing skills count as hits) and never the cover letter: the
        # letter may name a required skill precisely to say it is a gap ("I haven't used Go yet"),
        # so a mention there is not evidence. Cover-letter mentions are reported informationally.
        text = " " + re.sub(r"\s+", " ", self.resume_txt.lower()) + " "
        cover_text = ""
        if self.cover_md is not None:
            cover_text = " " + re.sub(r"\s+", " ", self.cover_body.lower()) + " "
        hit, miss, cover_mentions = [], [], []
        for s in req:
            s_low = s.lower().strip()
            variants = {s_low, s_low.replace("-", " "), s_low.replace(" ", ""), s_low.replace(".", "")}
            if any(v and _term_in_text(v, text) for v in variants):
                hit.append(s)
            else:
                miss.append(s)
            if cover_text and any(v and _term_in_text(v, cover_text) for v in variants):
                cover_mentions.append(s)
        cov = len(hit) / len(req)
        min_cov = float((self.qa_cfg.get("resume", {}) or {}).get("soft", {}).get("keyword_coverage_min", 0.6))
        self.extras["keyword_coverage"] = round(cov, 3)
        self.extras["cover_letter_mentions"] = cover_mentions
        only_in_letter = [s for s in cover_mentions if s in miss]
        detail = f"{cov:.0%} of {len(req)} required skills in resume.txt (min {min_cov:.0%}); missing: {', '.join(miss) or 'none'}"
        if only_in_letter:
            detail += f"; mentioned only in cover letter (not counted): {', '.join(only_in_letter)}"
        self.add("keyword_coverage", "soft", cov >= min_cov, detail)

    def check_cover_letter_structure(self) -> None:
        if self.cover_md is None:
            self.skip("cover_letter_structure", "hard", "cover_letter.md missing")
            return
        cl_cfg = (self.qa_cfg.get("cover_letter", {}) or {}).get("hard", {}) or {}
        facts = self.cover_fm.get("facts_used") or self.cover_fm.get("company_facts") or []
        min_facts = int(cl_cfg.get("company_facts_min", 2))
        self.add("cover_letter_company_facts", "hard", len(facts) >= min_facts,
                 f"{len(facts)} facts_used (min {min_facts})")
        if isinstance(self.posting, dict) and cl_cfg.get("names_role_and_company", True):
            body_low = self.cover_body.lower()
            company = str(self.posting.get("company", "")).lower()
            role = str(self.posting.get("title", "")).lower()
            ok_company = bool(company) and company in body_low
            # role match: full title, or the core noun phrase (strip parentheticals / level suffixes)
            role_core = re.sub(r"\(.*?\)", "", role).split(",")[0].strip()
            ok_role = bool(role) and (role in body_low or (role_core and role_core in body_low))
            self.add("cover_letter_names_company", "hard", ok_company, f"company '{self.posting.get('company')}' mentioned" if ok_company else "company name not found in body")
            self.add("cover_letter_names_role", "hard", ok_role, "role named" if ok_role else f"role '{self.posting.get('title')}' not found in body")
        if self.cover_fm.get("voice_verified") is False:
            self.add("voice_verified", "soft", False, "voice_verified=false (no voice samples yet)")
        if "?" in self.cover_body:
            self.add("no_rhetorical_questions", "soft", False, "question mark in cover letter body")

    def check_close_variant(self) -> None:
        """Soft: the letter's `close_variant` was already used in another letter to the same company
        (sibling job dirs). write-cover-letter rotates closes from the style guide's Close variants."""
        close = str(self.cover_fm.get("close_variant") or "").strip() if self.cover_md is not None else ""
        if not close:
            return
        from careeros.config import normalize_company

        posting_company = self.posting.get("company") if isinstance(self.posting, dict) else ""
        company = normalize_company(str(self.cover_fm.get("company") or posting_company or ""))
        repeats = []
        for d in sorted(self.job_dir.parent.iterdir()) if self.job_dir.parent.is_dir() else []:
            md = d / "cover_letter.md"
            if d == self.job_dir or not md.is_file():
                continue
            fm, _ = split_frontmatter(md.read_text(encoding="utf-8", errors="replace"))
            if str(fm.get("close_variant") or "").strip() == close and normalize_company(str(fm.get("company") or "")) == company:
                repeats.append(d.name)
        self.add("close_variant_repeated", "soft", not repeats,
                 f"close {close!r} not used before for this company" if not repeats
                 else f"close {close!r} already used for this company in: {', '.join(repeats)}")

    def check_bullet_shape(self) -> None:
        """Soft: each `- ` bullet line of resume.txt against resume_writing_rules.md (weak opener, no number or
        scale word, over `bullet_max_words`). Never fails QA: bullets are frozen profile text, so the fix is a
        stronger variant or a metric question in profile/master.yaml. Offenders are named by resume.json id."""
        if self.resume_txt is None:
            self.skip("bullet_shape", "soft", "resume.txt missing")
            return
        soft = ((self.qa_cfg.get("resume") or {}).get("soft") or {}) if isinstance(self.qa_cfg, dict) else {}
        weak = soft.get("weak_openers")
        weak = list(weak) if isinstance(weak, list) else list(DEFAULT_WEAK_OPENERS)
        scale = soft.get("scale_words")
        scale = list(scale) if isinstance(scale, list) else list(DEFAULT_SCALE_WORDS)
        try:
            max_words = int(soft.get("bullet_max_words", DEFAULT_BULLET_MAX_WORDS))
        except (TypeError, ValueError):
            max_words = DEFAULT_BULLET_MAX_WORDS
        ids_by_text: dict[str, str] = {}
        for e in self._resume_entries():
            for b in e.get("bullets") or []:
                if isinstance(b, dict) and b.get("id") and b.get("text"):
                    ids_by_text.setdefault(" ".join(_fid_words(b["text"])), str(b["id"]))
        found, n = [], 0
        for i, raw in enumerate(self.resume_txt.splitlines(), 1):
            m = re.match(r"\s*[-•*·]\s+(.*\S)", raw)
            if not m:
                continue
            n += 1
            line = m.group(1)
            issues = bullet_shape_issues(line, weak, max_words, scale)
            if issues:
                found.append({"id": ids_by_text.get(" ".join(_fid_words(line))), "line": line, "issues": issues,
                              "_n": i})
        self.extras["bullet_shape"] = [{k: v for k, v in f.items() if k != "_n"} for f in found]
        detail = "; ".join(f"{f['id'] or 'line ' + str(f['_n'])}: {', '.join(f['issues'])}"
                           + ("" if f["id"] else f" ({f['line'][:60]})") for f in found)
        self.add("bullet_shape", "soft", not found,
                 f"{n} bullets: verb-first, a number or scale word, <= {max_words} words" if not found
                 else f"{detail} (see .claude/skills/_shared/resume_writing_rules.md)")

    def check_answers_review(self) -> None:
        if not isinstance(self.answers, list):
            return
        pending = [i for i, a in enumerate(self.answers) if isinstance(a, dict) and (a.get("answer") is None or a.get("needs_review"))]
        if pending:
            self.add("answers_needs_review", "soft", False, f"answers needing review: {pending}")

    # ---- run -------------------------------------------------------------
    def run(self) -> dict[str, Any]:
        self.check_artifacts()
        self.check_banned()
        self.check_confidential()
        self.check_example_identity()
        self.check_word_counts()
        self.check_em_dashes()
        self.check_truth_trace()
        self.check_bullet_fidelity()
        self.check_entry_headers()
        self.check_skills_traced()
        self.check_standard_answers()
        self.check_numbers()
        self.check_estimates()
        self.check_tools()
        self.check_contact()
        self.check_pdf()
        self.check_keyword_coverage()
        self.check_bullet_shape()
        self.check_cover_letter_structure()
        self.check_close_variant()
        self.check_answers_review()
        hard_fail = [c for c in self.checks if c["level"] == "hard" and not c["ok"]]
        soft_fail = [c for c in self.checks if c["level"] == "soft" and not c["ok"]]
        skipped = [c for c in self.checks if c.get("skipped")]
        return {
            "job_dir": str(self.job_dir),
            "pass": not hard_fail,
            "artifacts": self.artifacts,
            "checks": self.checks,
            "summary": {"hard_fail": len(hard_fail), "soft_fail": len(soft_fail), "skipped": len(skipped)},
            "fail_reasons": [f"{c['check']}: {c['detail']}" for c in hard_fail],
            "warnings": [f"{c['check']}: {c['detail']}" for c in soft_fail],
            "keyword_coverage": self.extras.get("keyword_coverage"),
            "cover_letter_mentions": self.extras.get("cover_letter_mentions", []),
            "cover_letter_word_count": self.extras.get("cover_letter_word_count"),
            "orphan_numbers": self.extras["orphan_numbers"],
            "unknown_tools": self.extras["unknown_tools"],
            "banned_hits": self.extras["banned_hits"],
            "confidential_hits": self.extras.get("confidential_hits", []),
            "bullet_shape": self.extras.get("bullet_shape", []),
        }


def run_deterministic(job_dir: str | Path, root: str | Path | None = None) -> dict[str, Any]:
    job_dir = Path(job_dir)
    root_path = Path(root) if root else find_root(job_dir if job_dir.exists() else Path.cwd())
    if not job_dir.exists():
        return {
            "job_dir": str(job_dir), "pass": False, "artifacts": {},
            "checks": [{"check": "job_dir_exists", "level": "hard", "ok": False, "detail": f"{job_dir} does not exist"}],
            "summary": {"hard_fail": 1, "soft_fail": 0, "skipped": 0},
            "fail_reasons": [f"job_dir_exists: {job_dir} does not exist"], "warnings": [],
            "keyword_coverage": None, "orphan_numbers": [], "unknown_tools": [], "banned_hits": [], "confidential_hits": [],
            "bullet_shape": [],
        }
    return Checker(job_dir, root_path).run()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    root = None
    if "--root" in argv:
        i = argv.index("--root")
        root = argv[i + 1]
        del argv[i:i + 2]
    strict = "--strict" in argv
    argv = [a for a in argv if a != "--strict"]
    result = run_deterministic(argv[0], root)
    print(json.dumps(result, indent=2))
    return (0 if result["pass"] else 1) if strict else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
