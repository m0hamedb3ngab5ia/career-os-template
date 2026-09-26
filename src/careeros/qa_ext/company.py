"""Wrong-company leftovers: another company's name in this job's cover letter, generated answers or outreach.

    from careeros.qa_ext.company import check_wrong_company
    check_wrong_company(checker)      # checker: careeros.qa.Checker

Checks recorded:
    wrong_company               hard  a known company that is not this job's company is named in
                                      cover_letter.md (body), answers.json (generated answers) or outreach.json
                                      (draft text). extras["wrong_company_hits"] = [{file, name, context}].

That the letter names this job's company at all is the hard `cover_letter_names_company` check in careeros.qa;
it accepts every spelling `company_spellings` returns (aliases, domain stems) via `names_company`.

Candidate names: config/companies.yaml (dream_list, boards[].company, company_domains keys, prestige_tiers
lists, already_applied) plus `company` of every other job dir's posting.json (Finder duplicates "* 2*"
skipped). Not candidates: this job's company, its aliases and domain-derived spellings (and any name that
is a leading word-prefix of it, or it of them: "Citadel" for "Citadel Securities"), the candidate's own
employers / schools / projects / organisations and any name that appears in the profile text (a tool such
as Supabase), names the posting itself mentions, and `ignore_names` (LinkedIn, GitHub by default).

Matching is case-sensitive on the canonical spelling, on word boundaries. A name that is also an ordinary
English word ("Scale", "Square", "Linear") counts only as a proper noun: mid-sentence, and not on a
Title Case line such as an email subject.

Config (config/qa.yaml `consistency:`; every key optional):
    wrong_company: true            # false -> check skipped
    company_aliases: {}            # {<company>: [alias, ...]} extra spellings of a company
    ignore_names: []               # never flagged (added to LinkedIn, GitHub)
    common_word_names: []          # extra names treated as ordinary words (added to COMMON_WORD_NAMES)
    min_name_length: 3             # shorter names ("X") are never candidates
    scan_job_dirs: true            # also use other job dirs' posting.json company
    allow_posting_mentions: true   # a name this job's posting mentions is not a leftover
"""
from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path
from typing import Any, Iterable

from careeros.config import normalize_company
from careeros.qa_ext import outreach_items, outreach_texts
from careeros.safety.scam import registrable_domain

DEFAULT_IGNORE = ("LinkedIn", "GitHub")
# Company names that are also everyday words and can open a sentence or sit in a title-cased heading.
COMMON_WORD_NAMES = frozenset({
    "scale", "square", "block", "linear", "notion", "ramp", "runway", "cursor", "meta", "booking", "discord",
    "intel", "tower", "snowflake", "plaid", "cohere", "perplexity", "mistral", "adobe", "oracle", "uber",
    "twitch", "box", "target", "visa", "chase", "ally", "gap", "current", "chime", "affirm", "asana",
    "citadel", "millennium", "apple", "amazon", "google", "palantir", "anduril", "retool", "vanguard",
    "fidelity", "compass", "mercury", "brace", "wave", "signal", "zoom", "slack", "unity", "atlas", "sierra",
    "harvey", "glean", "hex", "modal", "replit", "together", "character", "scale ai",
})
# Host labels that name a hiring site, never the company ("careers.acme.com" is not the spelling "careers").
GENERIC_DOMAIN_STEMS = frozenset({"careers", "career", "jobs", "job", "apply", "boards", "board", "www", "hire",
                                  "hiring", "work", "team", "join", "recruiting"})
SMALL_WORDS = frozenset({"a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "at", "by", "with", "vs"})


# --------------------------------------------------------------------------- #
# config / name helpers
# --------------------------------------------------------------------------- #


def _cfg(ck: Any) -> dict[str, Any]:
    qa = ck.qa_cfg if isinstance(ck.qa_cfg, dict) else {}
    c = qa.get("consistency")
    return c if isinstance(c, dict) else {}


def _str_list(v: Any) -> list[str]:
    if isinstance(v, str):
        return [v] if v.strip() else []
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if isinstance(x, (str, int, float)) and str(x).strip()]


def _names_from_entries(v: Any) -> list[str]:
    """Names from a list of strings and/or {company: ...} dicts."""
    out = []
    for x in v if isinstance(v, list) else []:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
        elif isinstance(x, dict) and isinstance(x.get("company"), str) and x["company"].strip():
            out.append(x["company"].strip())
    return out


def _words(name: str) -> list[str]:
    return normalize_company(name).split()


def _compact(name: str) -> str:
    return "".join(_words(name))


def _related(a: str, b: str) -> bool:
    """Same company spelling: equal compact form, or one's words are a leading prefix of the other's."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    if "".join(wa) == "".join(wb):
        return True
    n = min(len(wa), len(wb))
    return wa[:n] == wb[:n]


def _domain_stem(d: Any) -> str | None:
    """The company label of a configured domain, as the scam gate reads it: `careers.acme.co.uk` -> `acme`.
    None for a bare label or a generic hiring-site word."""
    s = re.sub(r"^[a-z]+://", "", str(d or "").strip().lower()).split("/")[0]
    reg = registrable_domain(s) if s else ""
    if "." not in reg:
        return None
    stem = reg.split(".")[0]
    return stem if stem and stem not in GENERIC_DOMAIN_STEMS else None


def _jobs_dirs(ck: Any) -> list[Path]:
    dirs = [ck.job_dir.parent, ck.jobs_dir]
    out, seen = [], set()
    for d in dirs:
        key = str(d.resolve()) if d.exists() else str(d)
        if key not in seen and d.is_dir():
            seen.add(key)
            out.append(d)
    return out


def _job_dir_companies(ck: Any) -> list[str]:
    me = ck.job_dir.resolve()
    out = []
    for jobs in _jobs_dirs(ck):
        for d in sorted(jobs.iterdir()):
            if not d.is_dir() or d.resolve() == me or fnmatch.fnmatch(d.name, "* 2*"):
                continue
            try:
                posting = json.loads((d / "posting.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            c = posting.get("company") if isinstance(posting, dict) else None
            if isinstance(c, str) and c.strip():
                out.append(c.strip())
    return out


def _this_company(ck: Any) -> str:
    for src in (ck.posting, ck.cover_fm):
        if isinstance(src, dict) and isinstance(src.get("company"), str) and src["company"].strip():
            return src["company"].strip()
    return ""


def _this_spellings(company: str, companies: dict[str, Any], cfg: dict[str, Any]) -> list[str]:
    """This company's name, configured aliases and domain stems (every spelling that names it)."""
    names = [company]
    aliases = cfg.get("company_aliases")
    for k, v in (aliases.items() if isinstance(aliases, dict) else []):
        if _related(str(k), company):
            names += _str_list(v)
    domains = companies.get("company_domains")
    for k, v in (domains.items() if isinstance(domains, dict) else []):
        if _related(str(k), company):
            names += [s for s in (_domain_stem(x) for x in (v if isinstance(v, list) else [v])) if s]
    for b in companies.get("boards") or [] if isinstance(companies.get("boards"), list) else []:
        if isinstance(b, dict) and isinstance(b.get("company"), str) and _related(b["company"], company):
            stem = _domain_stem(b.get("domain"))
            if stem:
                names.append(stem)
    return list(dict.fromkeys(n for n in names if n.strip()))


def company_spellings(ck: Any, company: str) -> list[str]:
    """Every spelling that names `company` for this checker: the name itself, qa.yaml
    `consistency.company_aliases` and companies.yaml domain stems (company_domains, boards[].domain)."""
    return _this_spellings(company, ck.companies_cfg, _cfg(ck)) if company.strip() else []


def names_company(text: str, spellings: list[str]) -> str | None:
    """The first spelling `text` names (whole words, any case; or, for spellings of 4+ letters, the same
    letters with spacing/punctuation ignored: "Ledger-Line"), else None."""
    compact_text = re.sub(r"[^a-z0-9]", "", (text or "").lower())
    for s in spellings:
        if _name_rx(s, re.IGNORECASE).search(text or ""):
            return s
    for s in spellings:
        if len(_compact(s)) >= 4 and _compact(s) in compact_text:
            return s
    return None


def _candidate_names(ck: Any, companies: dict[str, Any], cfg: dict[str, Any]) -> list[str]:
    names = _names_from_entries(companies.get("dream_list"))
    names += _names_from_entries(companies.get("boards"))
    domains = companies.get("company_domains")
    names += [str(k) for k in (domains if isinstance(domains, dict) else {})]
    tiers = companies.get("prestige_tiers")
    for v in (tiers.values() if isinstance(tiers, dict) else []):
        names += _names_from_entries(v)
    names += _names_from_entries(companies.get("already_applied"))
    if cfg.get("scan_job_dirs", True) is not False:
        names += _job_dir_companies(ck)
    return list(dict.fromkeys(n for n in names if n.strip()))


def _profile_entity_names(profile: dict[str, Any]) -> list[str]:
    out = []
    for section, keys in (("experience", ("company", "team")), ("projects", ("name",)),
                          ("education", ("school",)), ("leadership", ("org", "name"))):
        for e in profile.get(section) or [] if isinstance(profile.get(section), list) else []:
            if isinstance(e, dict):
                out += [str(e[k]).strip() for k in keys if isinstance(e.get(k), str) and e[k].strip()]
    return out


def _profile_text(ck: Any) -> str:
    p = ck.profile
    parts = [p.header_text(), p.education_text(), p.skills_text(), p.stacks_text(), p.summary_text()]
    parts += [p.bullet_text(b) for b in p.bullets] + [p.bullet_text(n) for n in p.narratives]
    return " \n ".join(parts)


# --------------------------------------------------------------------------- #
# matching
# --------------------------------------------------------------------------- #


def _name_rx(name: str, flags: int = 0) -> re.Pattern[str]:
    body = r"\s+".join(re.escape(w) for w in name.split())
    return re.compile(r"(?<![A-Za-z0-9])" + body + r"(?![A-Za-z0-9])", flags)


def _at_sentence_start(text: str, start: int) -> bool:
    line = text[:start].rsplit("\n", 1)[-1]
    lead = line.rstrip().rstrip("\"'“‘([*_#>-•· \t")
    return lead == "" or lead[-1] in ".!?:"


def _title_case_line(text: str, start: int) -> bool:
    ls = text.rfind("\n", 0, start) + 1
    le = text.find("\n", start)
    line = text[ls:le if le != -1 else len(text)]
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]*", line) if w.lower() not in SMALL_WORDS]
    return len(words) >= 3 and sum(w[0].isupper() for w in words) >= 0.8 * len(words)


def _spans(rx: re.Pattern[str], text: str) -> list[tuple[int, int]]:
    return [m.span() for m in rx.finditer(text)]


def _overlaps(span: tuple[int, int], taken: Iterable[tuple[int, int]]) -> bool:
    return any(span[0] < e and s < span[1] for s, e in taken)


def _context(text: str, s: int, e: int, width: int = 40) -> str:
    return " ".join(text[max(0, s - width):e + width].split())


def _scan(label: str, text: str, candidates: list[str], this: list[str], own: list[str],
          common: set[str]) -> list[dict[str, str]]:
    taken: list[tuple[int, int]] = []
    for m in this:  # this company's spellings, any case
        taken += _spans(_name_rx(m, re.IGNORECASE), text)
    for m in own:  # the candidate's own employers/schools/projects, as spelled in the profile
        taken += _spans(_name_rx(m), text)
    hits: list[dict[str, str]] = []
    for name in sorted(candidates, key=len, reverse=True):
        is_common = name.lower() in common or normalize_company(name) in common
        for s, e in _spans(_name_rx(name), text):
            if _overlaps((s, e), taken):
                continue
            if is_common and (_at_sentence_start(text, s) or _title_case_line(text, s)):
                continue
            taken.append((s, e))
            if not any(h["name"] == name for h in hits):
                hits.append({"file": label, "name": name, "context": _context(text, s, e)})
    return hits


# --------------------------------------------------------------------------- #
# artifacts
# --------------------------------------------------------------------------- #


def _answer_docs(answers: Any) -> list[tuple[str, str]]:
    out = []
    for i, a in enumerate(answers if isinstance(answers, list) else []):
        if not isinstance(a, dict) or not isinstance(a.get("answer"), str) or not a["answer"].strip():
            continue
        if a.get("type") == "standard" or a.get("class") == "standard" or a.get("standard_key"):
            continue  # standard / EEO answers come verbatim from standard_answers.yaml
        out.append((f"answers.json#{i}", a["answer"]))
    return out


def _outreach_docs(ck: Any) -> list[tuple[str, str]]:
    if ck.outreach is None:
        raw = ck.outreach_raw
        return [("outreach.json", raw)] if raw is not None else []  # unparseable: scan it whole rather than not at all
    return [(f"outreach.json:{section}[{i}].{field}", text)
            for section, i, d in outreach_items(ck) for field, text in outreach_texts(d)]


# --------------------------------------------------------------------------- #
# check
# --------------------------------------------------------------------------- #


def check_wrong_company(ck: Any) -> None:
    cfg = _cfg(ck)
    ck.extras["wrong_company_hits"] = []
    has_cover = getattr(ck, "cover_md", None) is not None
    if cfg.get("wrong_company", True) is False:
        ck.skip("wrong_company", "hard", "disabled (qa.yaml consistency.wrong_company: false)")
        return

    company = _this_company(ck)
    companies = ck.companies_cfg
    spellings = company_spellings(ck, company)

    docs: list[tuple[str, str]] = []
    if has_cover and (ck.cover_body or "").strip():
        docs.append(("cover_letter.md", ck.cover_body))
    docs += _answer_docs(ck.answers)
    docs += _outreach_docs(ck)
    if not docs:
        ck.skip("wrong_company", "hard", "no cover letter, generated answers or outreach drafts")
        return
    if not company:
        ck.skip("wrong_company", "hard", "company unknown (no posting.json / frontmatter company)")
        return

    try:
        min_len = int(cfg.get("min_name_length", 3))
    except (TypeError, ValueError):
        min_len = 3
    ignore = {normalize_company(n) for n in (*DEFAULT_IGNORE, *_str_list(cfg.get("ignore_names")))}
    common = set(COMMON_WORD_NAMES) | {n.lower() for n in _str_list(cfg.get("common_word_names"))}
    own = _profile_entity_names(ck.profile.profile if isinstance(ck.profile.profile, dict) else {})
    profile_text = _profile_text(ck)
    posting_text = ""
    if cfg.get("allow_posting_mentions", True) is not False and isinstance(ck.posting, dict):
        posting_text = " ".join(str(ck.posting.get(k) or "") for k in ("title", "description_text"))

    candidates = []
    for name in _candidate_names(ck, companies, cfg):
        if len(name.strip()) < min_len or not normalize_company(name) or normalize_company(name) in ignore:
            continue
        if any(_related(name, s) for s in spellings) or any(_related(name, o) for o in own):
            continue
        if _name_rx(name).search(profile_text) or (posting_text and _name_rx(name).search(posting_text)):
            continue
        candidates.append(name)

    hits: list[dict[str, str]] = []
    for label, text in docs:
        hits += _scan(label, text, candidates, spellings, own, common) if candidates else []
    ck.extras["wrong_company_hits"] = hits
    ck.add("wrong_company", "hard", not hits,
           f"{len(candidates)} other company names checked; none in {', '.join(dict.fromkeys(l.split(':')[0].split('#')[0] for l, _ in docs))}"
           if not hits else "other company named (wrong-company leftover?): "
           + "; ".join(f"{h['file']}: '{h['name']}'" for h in hits))

