"""`careeros doctor`: a pass / warn / fail checklist of a checkout's setup.

    checks = run_doctor(root)            # list[Check]
    print(format_report(checks))         # or format_report(checks, quiet=True): FAIL lines only
    sys.exit(exit_code(checks))          # 1 if any FAIL, else 0

What it checks:
- profile/ and config/ exist; every YAML parses; the keys skills and the applier rely on are present.
- Untouched example data (FAIL): identity equal to examples/profile/master.yaml, any example.com email,
  entry ids from the example (acme, ...), standard_answers.yaml identical to the example.
- `# INSERT` / `# EDIT` lines copied verbatim from the example file (WARN, listed with file:line).
  Changing the value, or deleting the marker comment once you've confirmed it, clears the warning.
- categories.yaml bullet_priority ids that don't exist in profile/master.yaml (FAIL).
- Tools: claude (FAIL: every skill needs it), tectonic or pdflatex (WARN: PDF), gh and codex (WARN: /review).
- Voice samples: none in profile/voice/samples/ (WARN).
- Open `metric_questions` in profile/master.yaml (WARN "N metric questions open"), and questions naming a
  bullet id that does not exist (WARN). Optional bullet flags resume_default / weak / estimate must be booleans;
  an `estimate: true` bullet without a "~<number>" in its text (WARN: QA's estimate_marked cannot guard it).
- `**bold**` markup (careeros.markup) in bullet text, variants and summary_variants: unbalanced, empty or nested
  markers FAIL (the résumé render would fail); `**` in narratives WARNs (narratives feed prose, which stays plain).

The prepare-job and apply-job skills run `careeros doctor --quiet` first and stop on a nonzero exit,
so the fictional example candidate never reaches a real application.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

import yaml

from careeros.markup import MARKER, bold_allowed_at, format_path, iter_fields, strip_bold, validate_bold

PASS, WARN, FAIL = "pass", "warn", "fail"

CONFIG_FILES = ("targets", "categories", "companies", "qa", "pipeline")
PROFILE_FILES = ("master", "standard_answers", "confidential_terms")
KNOWN_ATS = {"greenhouse", "lever", "ashby", "custom"}
# The key set skills and the applier rely on (profile/standard_answers.yaml). Extra keys are fine.
STANDARD_KEYS = (
    "work_authorization", "sponsorship", "citizenship", "over_18", "relocate", "remote_hybrid", "start_date",
    "current_employer", "current_title", "years_experience_fulltime", "years_experience", "degree", "school",
    "major", "grad_year", "gpa", "salary_expectation", "previously_applied", "referral", "non_compete",
    "security_clearance", "linkedin", "github", "pronouns", "phone", "address",
)
IDENTITY_KEYS = ("name", "email", "phone", "linkedin", "github")
ENTRY_SECTIONS = ("experience", "projects", "education", "leadership")
MARKER_RE = re.compile(r"#\s*(INSERT\b|EDIT\b)")
BULLET_FLAGS = ("resume_default", "weak", "estimate")   # optional per-bullet booleans (resume_writing_rules.md)
EXAMPLE_EMAIL_RE = re.compile(r"[\w.+-]+@example\.com\b", re.I)


@dataclass(frozen=True)
class Check:
    level: str   # pass | warn | fail
    name: str
    detail: str


# --------------------------------------------------------------------------- #
# example reference
# --------------------------------------------------------------------------- #

def find_examples(root: Path) -> Path | None:
    """examples/ next to the checkout (root/examples, else the installed package's), or None."""
    from careeros.bootstrap import InitError, examples_dir

    try:
        return examples_dir(Path(root))
    except InitError:
        return None


def _safe_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None


def example_identity(examples: Path | None) -> dict[str, str]:
    """The fictional candidate's identity values (name, email, phone, links) from examples/profile/master.yaml."""
    if examples is None:
        return {}
    data = _safe_yaml(examples / "profile" / "master.yaml")
    ident = (data or {}).get("identity") or {} if isinstance(data, dict) else {}
    return {k: str(ident[k]) for k in IDENTITY_KEYS if ident.get(k)}


# --------------------------------------------------------------------------- #
# schema (shared with the YAML schema smoke test)
# --------------------------------------------------------------------------- #

def schema_problems(cfg: dict[str, Any], prof: dict[str, Any]) -> list[str]:
    """Required keys and shapes. `cfg` = {targets, categories, companies, qa, pipeline},
    `prof` = {master, standard_answers, confidential_terms}, each a parsed YAML mapping.
    Returns "<file>: <key> <problem>" strings; empty when everything the code reads is there."""
    out: list[str] = []

    def need(cond: Any, where: str) -> bool:
        if not cond:
            out.append(where)
        return bool(cond)

    t = cfg.get("targets") or {}
    for key in ("candidate", "location", "seniority", "categories", "thresholds", "tiers"):
        need(key in t, f"config/targets.yaml: {key} missing")
    if isinstance(t.get("location"), dict):
        need(isinstance(t["location"].get("blocked_countries", []), list), "config/targets.yaml: location.blocked_countries must be a list")
    if isinstance(t.get("seniority"), dict):
        need(isinstance(t["seniority"].get("exclude_title_keywords"), list), "config/targets.yaml: seniority.exclude_title_keywords must be a list")
    if isinstance(t.get("candidate"), dict):
        need(isinstance(t["candidate"].get("salary_dropdown_floor_usd"), int), "config/targets.yaml: candidate.salary_dropdown_floor_usd must be a whole number")

    cats = cfg.get("categories") or {}
    for name, c in cats.items():
        need(isinstance(c, dict) and isinstance(c.get("title_keywords"), list) and c["title_keywords"],
             f"config/categories.yaml: {name}.title_keywords missing or empty")
    for group in ("primary", "secondary", "excluded"):
        for name in (t.get("categories") or {}).get(group) or []:
            need(name in cats, f"config/targets.yaml: categories.{group} references unknown category {name}")

    co = cfg.get("companies") or {}
    need(isinstance(co.get("boards"), list), "config/companies.yaml: boards missing")
    for b in co.get("boards") or []:
        ok = isinstance(b, dict) and b.get("company") and b.get("ats") in KNOWN_ATS and (
            b.get("slug") or (b.get("ats") == "custom" and b.get("url")))
        need(ok, f"config/companies.yaml: boards entry {b} needs company, ats ({'|'.join(sorted(KNOWN_ATS))}) and slug (or url for custom)")
    tiers = co.get("prestige_tiers") or {}
    for tier in (co.get("prestige_scoring") or {}).get("auto_dream") or []:
        need(tier in tiers, f"config/companies.yaml: prestige_scoring.auto_dream tier {tier} missing from prestige_tiers")
    need(isinstance((co.get("blocklist") or {}).get("companies", []), list), "config/companies.yaml: blocklist.companies must be a list")

    for key in ("resume", "cover_letter", "banned_phrases"):
        need(key in (cfg.get("qa") or {}), f"config/qa.yaml: {key} missing")
    # bullet_shape keys are optional (careeros.qa has defaults); when present they must have the right type
    soft = ((cfg.get("qa") or {}).get("resume") or {}).get("soft") or {}
    if isinstance(soft, dict):
        if "bullet_max_words" in soft:
            v = soft["bullet_max_words"]
            need(isinstance(v, int) and not isinstance(v, bool) and v > 0,
                 "config/qa.yaml: resume.soft.bullet_max_words must be a positive whole number")
        for key in ("weak_openers", "scale_words"):
            if key in soft:
                need(isinstance(soft[key], list) and all(isinstance(w, str) and w.strip() for w in soft[key]),
                     f"config/qa.yaml: resume.soft.{key} must be a list of words/phrases")
    paths = (cfg.get("pipeline") or {}).get("paths") or {}
    for key in ("jobs_dir", "seen_file", "tracker_xlsx"):
        need(key in paths, f"config/pipeline.yaml: paths.{key} missing")

    m = prof.get("master") or {}
    for key in ("identity", "education", "experience", "skills"):
        need(key in m, f"profile/master.yaml: {key} missing")
    for key in ("name", "email", "phone"):
        need((m.get("identity") or {}).get(key), f"profile/master.yaml: identity.{key} missing")
    ids = [b.get("id") for sec in ("experience", "projects", "leadership") for e in m.get(sec) or []
           if isinstance(e, dict) for b in e.get("bullets") or [] if isinstance(b, dict)]
    need(ids and all(ids), "profile/master.yaml: every bullet needs an id")
    dup = sorted({i for i in ids if i and ids.count(i) > 1})
    need(not dup, f"profile/master.yaml: duplicate bullet ids {dup}")
    for sec in ("experience", "projects"):
        for e in m.get(sec) or []:
            for b in (e.get("bullets") or []) if isinstance(e, dict) else []:
                need(isinstance(b, dict) and isinstance(b.get("text"), str), f"profile/master.yaml: bullet {b.get('id') if isinstance(b, dict) else b} needs text")
    for sec in ("experience", "projects", "leadership"):
        for e in m.get(sec) or []:
            for b in (e.get("bullets") or []) if isinstance(e, dict) else []:
                for flag in BULLET_FLAGS if isinstance(b, dict) else ():
                    if flag in b:
                        need(isinstance(b[flag], bool), f"profile/master.yaml: {b.get('id')}.{flag} must be true or false")
    mq = m.get("metric_questions")
    if mq is not None and need(isinstance(mq, list), "profile/master.yaml: metric_questions must be a list of "
                                                     "{bullet_id, question}"):
        for i, q in enumerate(mq):
            need(isinstance(q, dict) and isinstance(q.get("bullet_id"), str) and q["bullet_id"].strip()
                 and isinstance(q.get("question"), str) and q["question"].strip(),
                 f"profile/master.yaml: metric_questions[{i}] needs a bullet_id and a question")

    sa = prof.get("standard_answers") or {}
    keys: list[str] = []
    for a in sa.get("answers") or []:
        if not need(isinstance(a, dict) and a.get("key"), f"profile/standard_answers.yaml: answer without key {a}"):
            continue
        keys.append(a["key"])
        for pat in a.get("match") or []:
            try:
                re.compile(pat, re.I)
            except re.error as e:
                out.append(f"profile/standard_answers.yaml: {a['key']}.match {pat!r} is not a valid regex ({e})")
    dup = sorted({k for k in keys if keys.count(k) > 1})
    need(not dup, f"profile/standard_answers.yaml: duplicate keys {dup}")
    missing = [k for k in STANDARD_KEYS if k not in keys]
    need(not missing, f"profile/standard_answers.yaml: answers missing keys {missing}")
    eeo = sa.get("eeo")
    if need(isinstance(eeo, dict), "profile/standard_answers.yaml: eeo missing"):
        for f in ("gender", "race_ethnicity", "veteran", "disability"):
            need(isinstance(eeo.get(f), dict) and "answer" in eeo[f], f"profile/standard_answers.yaml: eeo.{f}.answer missing")

    ct = prof.get("confidential_terms") or {}
    need(isinstance(ct.get("terms"), list), "profile/confidential_terms.yaml: terms must be a list")
    need(isinstance(ct.get("patterns"), list), "profile/confidential_terms.yaml: patterns must be a list")
    for i, pat in enumerate(ct.get("patterns") or []):
        try:
            re.compile(str(pat))
        except re.error as e:
            out.append(f"profile/confidential_terms.yaml: patterns[{i}] is not a valid regex ({e})")
    return out


# --------------------------------------------------------------------------- #
# individual checks
# --------------------------------------------------------------------------- #

def _walk_strings(obj: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            key = v.get("key") if isinstance(v, dict) and v.get("key") else i
            yield from _walk_strings(v, f"{path}[{key}]")
    elif isinstance(obj, str):
        yield path, obj


def _entry_ids(master: dict[str, Any], sections=ENTRY_SECTIONS) -> dict[str, list[str]]:
    return {sec: [str(e["id"]) for e in master.get(sec) or [] if isinstance(e, dict) and e.get("id")] for sec in sections}


def check_example_data(master: dict, answers: dict, ex_master: dict, ex_answers: dict) -> list[Check]:
    fails: list[str] = []
    ex_ident = (ex_master.get("identity") or {}) if isinstance(ex_master, dict) else {}
    ident = master.get("identity") or {}
    for k in IDENTITY_KEYS:
        if ex_ident.get(k) and str(ident.get(k)) == str(ex_ident[k]):
            fails.append(f"profile/master.yaml: identity.{k} is still the example value '{ex_ident[k]}'")
    for rel, data in (("profile/master.yaml", master), ("profile/standard_answers.yaml", answers)):
        for path, s in _walk_strings(data):
            if rel == "profile/master.yaml" and path == "identity.email" and s == ex_ident.get("email"):
                continue  # reported above
            for email in EXAMPLE_EMAIL_RE.findall(s):
                fails.append(f"{rel}: {path} uses an example.com email '{email}'")
    ex_ids = _entry_ids(ex_master or {})
    for sec, ids in _entry_ids(master).items():
        for i in ids:
            if i in ex_ids.get(sec, []):
                fails.append(f"profile/master.yaml: {sec} id '{i}' is from the example; replace the entry with your own")
    if ex_answers and answers == ex_answers:
        fails.append("profile/standard_answers.yaml: identical to the example file; every answer is still Alex Example's")
    if not fails:
        return [Check(PASS, "example_data", "no example identity, ids or answers left")]
    return [Check(FAIL, "example_data", f) for f in fails]


def check_placeholders(root: Path, examples: Path) -> list[Check]:
    """Lines carrying `# INSERT` / `# EDIT` in the example file that appear verbatim in the candidate's file."""
    out: list[Check] = []
    for rel in [f"profile/{n}.yaml" for n in PROFILE_FILES] + [f"config/{n}.yaml" for n in CONFIG_FILES]:
        ex, mine = examples / rel, root / rel
        if not ex.is_file() or not mine.is_file():
            continue
        marked = {ln.strip() for ln in ex.read_text(encoding="utf-8").splitlines()
                  if MARKER_RE.search(ln) and not ln.lstrip().startswith("#")}  # comment-only lines carry no value
        text = mine.read_text(encoding="utf-8").splitlines()
        same = [n for n, ln in enumerate(text, 1) if ln.strip() in marked]
        if same:
            where = ", ".join(f"{n} {_line_key(text, n - 1)}" for n in same)
            out.append(Check(WARN, "unchanged_placeholder",
                             f"{rel}: {len(same)} `# INSERT` line(s) still identical to the example (line key): {where}"))
    if not out:
        out.append(Check(PASS, "unchanged_placeholder", "no example placeholder line left unchanged"))
    return out


def _line_key(lines: list[str], i: int) -> str:
    """Short label for line i: its key (`  - id: acme  # INSERT` -> `id`), qualified by the owning entry
    for repeated keys (`answer` under `- key: phone` -> `phone.answer`); a bare list item -> 20 chars."""
    line = lines[i].strip()
    m = re.match(r"-?\s*([\w.-]+)\s*:", line)
    if not m:
        return line.split("#")[0].strip()[:20]
    key = m.group(1)
    if key in ("answer", "prefer", "match_not"):
        for prev in reversed(lines[:i]):
            owner = re.match(r"\s*- key:\s*(\w+)", prev) or re.match(r"\s+(\w+):\s*(#.*)?$", prev)
            if owner:
                return f"{owner.group(1)}.{key}"
    return key


def check_bullet_priority(categories: dict, master: dict) -> list[Check]:
    known: set[str] = set()
    for sec in ENTRY_SECTIONS:
        for e in master.get(sec) or []:
            if isinstance(e, dict):
                known.add(str(e.get("id")))
                known.update(str(b.get("id")) for b in e.get("bullets") or [] if isinstance(b, dict))
    out = []
    for name, c in categories.items():
        if not isinstance(c, dict):
            continue
        unknown = [str(i) for i in c.get("bullet_priority") or [] if str(i) not in known]
        if unknown:
            out.append(Check(FAIL, "bullet_priority", f"config/categories.yaml: {name}.bullet_priority has id(s) "
                                                      f"{', '.join(unknown)} that are not in profile/master.yaml"))
    return out or [Check(PASS, "bullet_priority", "every categories.yaml bullet_priority id exists in master.yaml")]


def check_metric_questions(master: dict) -> list[Check]:
    """WARN while the candidate owes answers to metric questions (resume_writing_rules.md: never estimate a
    number for them); WARN for a question whose bullet_id is not a bullet (e.g. left over from the example)."""
    qs = [q for q in master.get("metric_questions") or [] if isinstance(q, dict)]
    if not qs:
        return [Check(PASS, "metric_questions", "no open metric questions in profile/master.yaml")]
    bullets = {str(b.get("id")) for sec in ("experience", "projects", "leadership") for e in master.get(sec) or []
               if isinstance(e, dict) for b in e.get("bullets") or [] if isinstance(b, dict)}
    n = len(qs)
    out = [Check(WARN, "metric_questions", f"{n} metric question{'s' if n != 1 else ''} open in profile/master.yaml")]
    unknown = [str(q.get("bullet_id")) for q in qs if str(q.get("bullet_id")) not in bullets]
    if unknown:
        out.append(Check(WARN, "metric_questions", f"bullet_id {', '.join(unknown)} is not a bullet in "
                                                   "profile/master.yaml: fix the id or delete the question"))
    return out


def check_estimates(master: dict) -> list[Check]:
    """WARN for `estimate: true` bullets whose text has no "~<number>" (resume_writing_rules.md, OVERRIDE rule 3)."""
    bad = [str(b.get("id")) for sec in ("experience", "projects", "leadership") for e in master.get(sec) or []
           if isinstance(e, dict) for b in e.get("bullets") or []
           if isinstance(b, dict) and b.get("estimate") is True and not re.search(r"~\s*\$?\d", strip_bold(b.get("text")))]
    return [Check(WARN, "estimates", f"profile/master.yaml: {i} has estimate: true but no ~number in its text; "
                                     "write the estimated number as ~N (e.g. ~40%)") for i in bad]


def check_bold(master: dict) -> list[Check]:
    """FAIL for invalid `**bold**` markup in bullet text / variants / summary_variants, and for `**` in any other
    field (render.py rejects both: markup.bold_allowed); WARN for `**` in narratives (cover letters and answers
    draw on them and must stay plain prose)."""
    ids: dict[str, str] = {}  # "experience[0].bullets[1]" -> bullet id, for readable messages
    for sec in ("experience", "projects", "leadership"):
        for i, e in enumerate(master.get(sec) or []):
            for j, b in enumerate((e.get("bullets") or []) if isinstance(e, dict) else []):
                if isinstance(b, dict) and b.get("id") is not None:
                    ids[f"{sec}[{i}].bullets[{j}]"] = str(b.get("id"))
    fails: list[str] = []
    for keys, s in iter_fields(master):
        if MARKER not in s or keys[:1] == ("narratives",):
            continue
        path = format_path(keys)
        if not bold_allowed_at(keys, "master"):
            fails.append(f"{path}: '**' is allowed only in bullet text, variants and summary_variants "
                         "(render.py rejects it anywhere else): drop it")
        elif (err := validate_bold(s)):
            head = format_path(keys[:4])
            fails.append(f"{ids[head]}.{format_path(keys[4:])}: {err}" if len(keys) > 4 and head in ids
                         else f"{path}: {err}")
    out = [Check(FAIL, "bold_markup", f"profile/master.yaml: {f}") for f in fails]
    narr = [str(n.get("id")) for n in master.get("narratives") or []
            if isinstance(n, dict) and MARKER in str(n.get("text") or "")]
    if narr:
        out.append(Check(WARN, "bold_markup", f"profile/master.yaml: narratives {', '.join(narr)} contain '**'; "
                                              "narratives feed cover letters and answers, which stay plain: drop it"))
    return out or [Check(PASS, "bold_markup", "**bold** markup in bullets and summaries is valid")]


def check_tools(which: Callable[[str], str | None], env: dict[str, str] | None = None) -> list[Check]:
    out = []
    latex = [t for t in ("tectonic", "pdflatex") if which(t)]
    out.append(Check(PASS, "latex", f"{latex[0]} found") if latex else Check(
        WARN, "latex", "neither tectonic nor pdflatex on PATH: résumés stay .tex, no PDF (brew install tectonic)"))
    inside = (os.environ if env is None else env).get("CLAUDECODE") == "1"  # set by Claude Code in its shells
    if which("claude"):
        out.append(Check(PASS, "claude", "claude CLI found"))
    elif inside:
        out.append(Check(PASS, "claude", "running inside Claude Code (no `claude` on PATH; headless `claude -p` needs it)"))
    else:
        out.append(Check(FAIL, "claude", "claude (Claude Code CLI) not on PATH: every skill needs it. Install Claude Code, then `claude` once to log in"))
    for tool in ("gh", "codex"):
        out.append(Check(PASS, tool, f"{tool} found") if which(tool) else Check(
            WARN, tool, f"{tool} not on PATH: only needed for /review (code review of PRs)"))
    return out


def check_runs(pipeline: dict[str, Any]) -> list[Check]:
    """`pipeline.yaml: runs` and `llm` parse (careeros.runs.config); the headless command streams."""
    from careeros.config import ConfigError
    from careeros.runs.config import load_runs_config

    try:
        cfg = load_runs_config(type("_P", (), {"pipeline": pipeline})())
    except ConfigError as e:
        return [Check(FAIL, "runs", str(e))]
    cmd = cfg.headless_cmd
    fmt = cmd[cmd.index("--output-format") + 1] if "--output-format" in cmd[:-1] else "text"
    if fmt != "stream-json" or "--verbose" not in cmd:
        return [Check(WARN, "runs", "llm.headless_cmd should use --output-format stream-json --verbose: "
                                    "`careeros run` reads the live event stream and its final result event")]
    from careeros.runs.schedule import load_schedule

    try:
        sched = load_schedule(type("_P", (), {"pipeline": pipeline})())
    except ConfigError as e:
        return [Check(FAIL, "schedule", str(e))]
    on = [k for k, j in sched.jobs.items() if j.enabled]
    return [Check(PASS, "runs", f"runs config ok (preset {cfg.preset}); headless: {' '.join(cmd[:2])} ..."),
            Check(PASS, "schedule", f"schedule ok: {', '.join(on) or 'nothing'} (install: careeros schedule install)")]


def check_voice(root: Path) -> Check:
    d = root / "profile" / "voice" / "samples"
    n = sum(1 for p in d.iterdir() if p.is_file() and not p.name.startswith(".")) if d.is_dir() else 0
    if n:
        return Check(PASS, "voice_samples", f"{n} voice sample(s) in profile/voice/samples/")
    return Check(WARN, "voice_samples", "0 voice samples in profile/voice/samples/: cover letters are flagged "
                                        "voice_verified: false. Add 2-5 letters or emails you wrote, then /learn-voice")


# --------------------------------------------------------------------------- #
# run + report
# --------------------------------------------------------------------------- #

def run_doctor(root: Path, which: Callable[[str], str | None] = shutil.which,
               examples: Path | None = None, env: dict[str, str] | None = None) -> list[Check]:
    root = Path(root)
    examples = examples if examples is not None else find_examples(root)
    checks: list[Check] = []
    missing = [d for d in ("profile", "config") if not (root / d).is_dir()]
    if missing:
        checks.append(Check(FAIL, "setup", f"{' and '.join(d + '/' for d in missing)} missing under {root}: "
                                           "run `careeros init` (or `careeros init --link <your-private-dir>`)"))
        return checks + check_tools(which, env)
    checks.append(Check(PASS, "setup", "profile/ and config/ present"))

    data: dict[str, Any] = {}
    bad = False
    for rel in [f"config/{n}.yaml" for n in CONFIG_FILES] + [f"profile/{n}.yaml" for n in PROFILE_FILES]:
        p = root / rel
        if not p.is_file():
            checks.append(Check(FAIL, "yaml", f"{rel} missing (copy it from examples/{rel})"))
            bad = True
            continue
        try:
            d = yaml.safe_load(p.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            hint = (" (a value starting with ** must be quoted: text: \"**Python** ...\")"
                    if "scanning an alias" in str(e) else "")
            checks.append(Check(FAIL, "yaml", f"{rel} does not parse: {' '.join(str(e).split())[:160]}{hint}"))
            bad = True
            continue
        if not isinstance(d, dict):
            checks.append(Check(FAIL, "yaml", f"{rel} must be a mapping (key: value), got {type(d).__name__}"))
            bad = True
            continue
        data[rel] = d
    if bad:
        return checks + check_tools(which, env) + [check_voice(root)]
    checks.append(Check(PASS, "yaml", "every config/ and profile/ YAML parses"))

    cfg = {n: data[f"config/{n}.yaml"] for n in CONFIG_FILES}
    prof = {n: data[f"profile/{n}.yaml"] for n in PROFILE_FILES}
    probs = schema_problems(cfg, prof)
    checks += [Check(FAIL, "schema", p) for p in probs] or [Check(PASS, "schema", "required keys present")]

    master, answers = prof["master"], prof["standard_answers"]
    if examples is not None:
        ex_master = _safe_yaml(examples / "profile" / "master.yaml") or {}
        ex_answers = _safe_yaml(examples / "profile" / "standard_answers.yaml") or {}
        checks += check_example_data(master, answers, ex_master, ex_answers)
        checks += check_placeholders(root, examples)
    else:
        checks.append(Check(WARN, "example_data", "no examples/ found to compare against; example data not checked"))
    checks += check_bullet_priority(cfg["categories"], master)
    checks += check_runs(cfg["pipeline"])
    if not probs:
        checks += check_metric_questions(master)
        checks += check_estimates(master)
        checks += check_bold(master)
    checks += check_tools(which, env)
    checks.append(check_voice(root))
    return checks


def exit_code(checks: list[Check]) -> int:
    return 1 if any(c.level == FAIL for c in checks) else 0


def format_report(checks: list[Check], quiet: bool = False, root: Path | None = None) -> str:
    n = {lvl: sum(1 for c in checks if c.level == lvl) for lvl in (FAIL, WARN, PASS)}
    shown = [c for c in checks if c.level == FAIL] if quiet else checks
    if quiet and not shown:
        return ""
    lines = [] if quiet or root is None else [f"careeros doctor: {root}", ""]
    lines += [f"  {c.level.upper():<4}  {c.name:<22} {c.detail}" for c in shown]
    summary = f"{n[FAIL]} fail, {n[WARN]} warn, {n[PASS]} pass"
    if n[FAIL]:
        summary += ": fix every FAIL, then run `careeros doctor` again (docs/GETTING_STARTED.md)"
    elif n[WARN]:
        summary += ": ready; the warnings are worth a look"
    else:
        summary += ": ready"
    lines += ["", summary]
    return "\n".join(lines)
