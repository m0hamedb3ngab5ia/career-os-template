"""Cross-document consistency: the same facts agree across one job's documents.

`check_cross_doc(ck)` adds to a `careeros.qa.Checker`:

- `letter_experiences_on_resume` (soft): every bullet / entry id the cover letter cites belongs to an entry
  (experience, project, leadership, education) that is on this job's résumé.json. Narratives and ids unknown to
  the profile are ignored (truth_trace reports those).
- `employer_title_consistent` (hard): where the letter, an answer or an outreach draft ties the candidate to one of
  their employers/schools with a title, a degree or a year, it agrees with the résumé entry header (profile entry
  as fallback). Titles count only when anchored to the candidate ("I'm a <title> at <org>", "at <org> as a
  <title>", "at <org>, where I work as a <title>"); a mismatch is hard when the prose adds a seniority word or
  changes the role noun. Years count only after a date word ("in 2024", "since 2024") within `year_window`
  characters of the nearest employer/school named in the sentence.
- `employer_title_uncertain` (soft, only on findings): a title that differs only by a descriptor ("backend
  engineer" vs "Software Engineer"), or an unanchored title-case title next to the employer.
- `numbers_consistent` (hard): a sentence attributed to a bullet (>= `min_overlap` shared content words) states the
  bullet's numbers with the same value (2M == 2 million == two million). The reference is the résumé.json bullet,
  or the profile master text when the bullet is not on the résumé. Numbers are paired by kind (%, $, x) or by
  the noun that follows them. Only the clause(s) of the sentence that overlap the bullet most are compared
  (clauses split on ";", ", and", ", while", " but ", dashes), and a number whose value the posting text or any
  artifact's `facts_used` states is a company fact, never a mismatch.
- `numbers_paraphrased` (soft, only on findings): a vague or hedged restatement ("nearly half", "dozens of",
  "nearly 40") of an exact bullet number. Repeating the bullet's own hedge class ("about 2" for "~2", "more than 40%" for "over 40%") is
  not reported; flipping a bound ("up to 40%" -> "over 40%") is.

Config (`config/qa.yaml: consistency`, all optional): enabled (true), min_overlap (3), year_window (40),
role_nouns, seniority_words (lists; defaults below). Findings go to `ck.extras["consistency"]`:
{docs, config, letter_off_resume, title_mismatches, title_uncertain, number_mismatches, number_paraphrases}.
"""
from __future__ import annotations

import re
from typing import Any

from careeros.qa import cited_ids_cover_letter
from careeros.qa_ext import outreach_data, outreach_items, outreach_texts

DEFAULT_ROLE_NOUNS = (
    "engineer", "developer", "intern", "analyst", "scientist", "manager", "designer", "architect", "consultant",
    "researcher", "assistant", "lead", "director", "specialist", "administrator", "associate", "fellow", "co-op",
    "programmer", "technician", "treasurer", "president", "officer", "founder", "tutor", "instructor",
)
DEFAULT_SENIORITY_WORDS = (
    "senior", "sr", "staff", "principal", "lead", "junior", "jr", "head", "chief", "director", "manager", "vp",
    "ii", "iii", "iv", "distinguished", "executive",
)
DEFAULT_MIN_OVERLAP = 3
DEFAULT_YEAR_WINDOW = 40

CHECKS = ("letter_experiences_on_resume", "employer_title_consistent", "numbers_consistent")

STOP = {
    "a", "an", "the", "and", "or", "of", "for", "with", "in", "on", "at", "to", "by", "from", "as", "is", "are",
    "was", "were", "be", "been", "that", "this", "these", "those", "it", "its", "i", "my", "me", "we", "our", "us",
    "you", "your", "per", "each", "every", "across", "into", "than", "then", "so", "but", "not", "no", "all",
    "some", "which", "who", "while", "when", "where", "about", "over", "under", "nearly", "almost", "roughly",
    "around", "approximately", "more", "less", "fewer", "used", "using", "via", "had", "have", "has", "did",
}
SCALE = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "hundred": 1e2}
SUFFIX = {"k": 1e3, "m": 1e6, "b": 1e9}
WORD_NUM = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen".split())}
WORD_NUM.update({w: 10 * i for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), 2)})
WORD_NUM["dozen"] = 12
VAGUE_PCT = {"half": 50.0, "third": 33.0, "quarter": 25.0, "majority": 60.0, "most": 60.0}
VAGUE_QTY = {"dozens", "hundreds", "thousands", "millions", "billions", "several", "many", "handful", "countless",
             "numerous"}
HEDGE_1 = {"nearly", "almost", "about", "roughly", "around", "approximately", "over", "under", "~", "upwards",
           "approx", "some"}
HEDGE_2 = {("more", "than"), ("less", "than"), ("fewer", "than"), ("close", "to"), ("up", "to"), ("north", "of")}
# hedge direction: a restatement may repeat the bullet's own hedge class, never flip a bound ("up to 40%" -> "over 40%")
HEDGE_LOWER = {"over", "upwards", "more than", "north of"}
HEDGE_UPPER = {"under", "less than", "fewer than", "up to"}


def hedge_class(hedge: str) -> str:
    """'lower' (a floor: over, more than), 'upper' (a ceiling: under, up to) or 'approx' (about, ~, nearly...)."""
    return "lower" if hedge in HEDGE_LOWER else "upper" if hedge in HEDGE_UPPER else "approx"
DATE_WORDS = {"in", "since", "from", "until", "till", "through", "to", "during", "of", "summer", "fall", "autumn",
              "spring", "winter", "class", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept",
              "oct", "nov", "dec", "january", "february", "march", "april", "june", "july", "august", "september",
              "october", "november", "december", "(", "-", "–"}
DEGREE_RX = {
    "associate": re.compile(r"\bassociate'?s?\s+degree\b|\bA\.A\.S?\b", re.I),
    "bachelor": re.compile(r"(?i:\bbachelor(?:'s|s)?\b|\bundergrad\w*)|(?<![A-Za-z.])(?:B\.S\.?|B\.A\.?|B\.E\.?|B\.Sc\.?|BS|BA|BSc|BEng)(?![A-Za-z])"),
    "master": re.compile(r"(?i:\bmaster(?:'s|s)?\b)|(?<![A-Za-z.])(?:M\.S\.?|M\.A\.?|M\.Sc\.?|M\.Eng\.?|MS|MSc|MEng|MBA)(?![A-Za-z])"),
    "doctorate": re.compile(r"\bph\.?\s?d\b|\bdoctora(?:te|l)\b", re.I),
}
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])|\n+")
TOKEN_RE = re.compile(r"~|\$|\d[\d,]*(?:\.\d+)?(?:%|[kKmMbB](?![A-Za-z])|x(?![A-Za-z])|\+)?|[A-Za-z][A-Za-z'-]*|[(–-]")
# clause boundaries inside one sentence: a company fact and a bullet claim often share a sentence
CLAUSE_SPLIT = re.compile(r";|,\s+(?:and|while|whereas)\s+|\s+but\s+|\s*—\s*|\s+–\s+|\s+--?\s+")
YEAR_RE = re.compile(r"(?<![\w$.,])((?:19|20)\d{2})(?![\d%+]|[.,]\d|\w)")


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def _sing(w: str) -> str:
    w = w.lower().strip("'-")
    if w.endswith("'s"):
        w = w[:-2]
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def _content(text: str) -> set[str]:
    return {_sing(w) for w in re.findall(r"[A-Za-z][A-Za-z'-]+", text or "") if w.lower() not in STOP and len(w) > 2}


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT_SPLIT.split(text or "") if s.strip()]


def _year_of(v: Any) -> int | None:
    m = re.search(r"(?:19|20)\d{2}", str(v or ""))
    return int(m.group(0)) if m else None


def _fmt(v: float) -> str:
    return f"{v:g}"


# --------------------------------------------------------------------------- #
# number parsing
# --------------------------------------------------------------------------- #

def parse_numbers(text: str) -> list[dict[str, Any]]:
    """Quantities in `text`: [{value, kind ('%'|'$'|'x'|''), unit: set[str], raw, hedged, hedge, vague, estimate,
    glued}].
    `unit` = the next two content words (singular) after the number and its scale word."""
    spans = [(m.group(), m.start()) for m in TOKEN_RE.finditer(text or "")]
    toks = [t for t, _ in spans]
    # a number glued to a preceding letter (S3, EC2, TLS1.3, USD5M): kept as a quantity everywhere, but never a
    # company fact in _context_values, where a product name would excuse a changed bullet number
    glued_at = {i for i, (_, pos) in enumerate(spans) if pos and text[pos - 1].isalpha()}
    low = [t.lower() for t in toks]
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(toks):
        t, lt = toks[i], low[i]
        start = i
        value: float | None = None
        kind = ""
        vague = False
        m = re.fullmatch(r"(\d[\d,]*(?:\.\d+)?)(%|[kKmMbB]|x|\+)?", t)
        if m:
            try:
                value = float(m.group(1).replace(",", ""))
            except ValueError:
                i += 1
                continue
            suf = (m.group(2) or "").lower()
            if suf == "%":
                kind = "%"
            elif suf in SUFFIX:
                value *= SUFFIX[suf]
            elif suf == "x":
                kind = "x"
        elif lt in WORD_NUM or (lt.split("-")[0] in WORD_NUM and "-" in lt):
            parts = lt.split("-")
            if not all(p in WORD_NUM for p in parts):
                i += 1
                continue
            value = float(sum(WORD_NUM[p] for p in parts))
        elif lt in VAGUE_PCT:
            value, kind, vague = VAGUE_PCT[lt], "%", True
        elif lt in VAGUE_QTY:
            value, vague = None, True
        else:
            i += 1
            continue
        j = i + 1
        if j < len(toks) and low[j] in SCALE and not vague:
            value = (value or 1) * SCALE[low[j]]
            j += 1
        elif j < len(toks) and low[j] in SCALE and vague:
            j += 1
        if j < len(toks) and low[j] in ("percent", "percentage") and not kind:
            kind, j = "%", j + 1
        if start and toks[start - 1] == "$":
            kind = "$"
        prev1 = low[start - 1] if start >= 1 else ""
        prev2 = low[start - 2] if start >= 2 else ""
        if prev1 in ("a", "an") and start >= 2:  # "nearly a third", "about a dozen"
            prev1, prev2 = prev2, low[start - 3] if start >= 3 else ""
        hedged = prev1 in HEDGE_1 or (prev2, prev1) in HEDGE_2 or prev1 == "~"
        hedge = ""
        if hedged:
            hedge = f"{prev2} {prev1}" if (prev2, prev1) in HEDGE_2 else prev1
        unit: list[str] = []
        k = j
        while k < len(toks) and len(unit) < 2 and k < j + 5:
            w = low[k]
            if re.match(r"[a-z]", w) and w not in STOP and w not in SCALE:
                unit.append(_sing(w))
            elif re.match(r"[\d$~]", w):
                break
            k += 1
        out.append({"value": value, "kind": kind, "unit": set(unit), "hedged": hedged, "vague": vague,
                    "estimate": prev1 == "~", "hedge": hedge, "glued": start in glued_at,
                    "raw": (hedge + (" " if hedge != "~" else "") if hedge else "") + " ".join(toks[start:j])})
        i = j
    return out


def _same_hedge(p: dict[str, Any], r: dict[str, Any]) -> bool:
    """The restatement repeats the bullet's own hedge: the same class, or approximate for a `~` / approximate bullet."""
    if not (r["estimate"] or r["hedged"]):
        return False
    return hedge_class(p["hedge"]) == hedge_class(r["hedge"] or "~")


def _paired(p: dict[str, Any], r: dict[str, Any]) -> bool:
    if p["kind"] != r["kind"]:
        return False
    if p["kind"] in ("%", "$", "x"):
        return True
    return bool(p["unit"] & r["unit"])


# --------------------------------------------------------------------------- #
# documents
# --------------------------------------------------------------------------- #

def _ids(obj: dict[str, Any]) -> set[str]:
    return {str(x) for k in ("bullet_ids", "narrative_ids") for x in (obj.get(k) or []) if isinstance(x, (str, int))}


def prose_docs(ck: Any) -> list[tuple[str, str, set[str]]]:
    """(name, text, cited ids) for the cover letter body, each non-standard answer and each outreach draft /
    top-level follow-up."""
    docs: list[tuple[str, str, set[str]]] = []
    if ck.cover_md is not None:
        docs.append(("cover_letter.md", ck.cover_body, cited_ids_cover_letter(ck.cover_fm)))
    if isinstance(ck.answers, list):
        for i, a in enumerate(ck.answers):
            if isinstance(a, dict) and a.get("answer") and a.get("type") != "standard":
                docs.append((f"answers.json#{i}", str(a["answer"]), _ids(a)))
    for section, i, d in outreach_items(ck):  # drafts[] (a bare list counts) + top-level followups[]
        text = "\n".join(t for _, t in outreach_texts(d))
        if text.strip():
            label = f"outreach.json#{i}" if section == "drafts" else f"outreach.json#{section}[{i}]"
            docs.append((label, text, _ids(d)))
    return docs


def _resume(ck: Any) -> dict[str, Any] | None:
    rj = ck.resume_json
    return rj if isinstance(rj, dict) and "__parse_error__" not in rj else None


def _resume_entries(rj: dict[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for section in ("experience", "projects", "leadership", "education"):
        out.extend((section, e) for e in (rj or {}).get(section) or [] if isinstance(e, dict))
    return out


# --------------------------------------------------------------------------- #
# 1. letter_experiences_on_resume
# --------------------------------------------------------------------------- #

def _check_letter_entries(ck: Any, ex: dict[str, Any]) -> None:
    name = "letter_experiences_on_resume"
    rj = _resume(ck)
    if ck.cover_md is None or rj is None:
        ck.skip(name, "soft", "cover_letter.md or resume.json missing")
        return
    on_resume = {str(e.get("id")) for _, e in _resume_entries(rj) if e.get("id")}
    prof = ck.profile
    edu_ids = prof.education_ids()
    off = []
    for bid in sorted(cited_ids_cover_letter(ck.cover_fm)):
        if bid in prof.bullets:
            entry = str(prof.bullet_parent[bid].get("id") or "")
        elif bid in prof.parents or bid in edu_ids:
            entry = bid
        else:
            continue  # narrative or unknown id
        if entry and entry not in on_resume:
            off.append({"id": bid, "entry": entry})
    ex["letter_off_resume"] = off
    ck.add(name, "soft", not off,
           "every experience the cover letter cites is on the résumé" if not off else
           "; ".join(f"cover letter cites {o['id']} (entry {o['entry']}), not on this résumé" for o in off))


# --------------------------------------------------------------------------- #
# 2. employer_title_consistent
# --------------------------------------------------------------------------- #

def _orgs(ck: Any, rj: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """lower-cased org name -> {name, titles: set, years: [(lo, hi|None)], degrees: set, check_years: bool}."""
    orgs: dict[str, dict[str, Any]] = {}

    def add(section: str, e: dict[str, Any], src: dict[str, Any] | None) -> None:
        key = {"experience": "company", "education": "school", "leadership": "org", "projects": "name"}[section]
        org = str(e.get(key) or (src or {}).get(key) or "").strip()
        if not org:
            return
        rec = orgs.setdefault(org.lower(), {"name": org, "titles": set(), "years": [], "degrees": set(),
                                            "check_years": section != "projects"})
        for s in (e, src or {}):
            for t in ("title", "title_display", "role"):
                if s.get(t):
                    rec["titles"].add(str(s[t]).strip())
            if s.get("degree"):
                rec["degrees"].update(_degree_levels(str(s["degree"])))
        if section != "projects":
            s = src or {}
            lo = _year_of(e.get("start") or e.get("date")) or _year_of(s.get("start") or s.get("date"))
            end = e.get("end") if e.get("end") not in (None, "") else s.get("end")
            if end in (None, "") and (e.get("date") or s.get("date")):
                hi = lo  # single-date entry (leadership)
            elif end in (None, "") or str(end).strip().lower() in ("present", "current"):
                hi = None
            else:
                hi = _year_of(end)
            if lo is not None or hi is not None:
                rec["years"].append((lo, hi))

    prof = ck.profile.profile
    edu = {e.get("id"): e for e in prof.get("education") or [] if isinstance(e, dict)}
    seen = set()
    for section, e in _resume_entries(rj):
        eid = e.get("id")
        src = edu.get(eid) if section == "education" else ck.profile.parents.get(str(eid or ""))
        add(section, e, src)
        seen.add(eid)
    for section in ("experience", "projects", "leadership", "education"):
        for e in prof.get(section) or []:
            if isinstance(e, dict) and e.get("id") not in seen:
                add(section, e, None)
    return orgs


def _degree_levels(text: str) -> set[str]:
    return {lvl for lvl, rx in DEGREE_RX.items() if rx.search(text)}


def _norm_words(title: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", title.lower()) if w not in ("a", "an", "the", "my", "of")]


def _compare_title(found: str, known: set[str], seniority: set[str]) -> str:
    """'ok' | 'hard' | 'soft'."""
    fw = _norm_words(found)
    if not fw or not known:
        return "ok"
    kw = {w for t in known for w in _norm_words(t)}
    extra = [w for w in fw if w not in kw]
    if not extra:
        return "ok"
    if any(w in seniority for w in extra) or fw[-1] not in kw:
        return "hard"
    return "soft"


def _check_titles(ck: Any, ex: dict[str, Any], docs: list[tuple[str, str, set[str]]], cfg: dict[str, Any]) -> None:
    name = "employer_title_consistent"
    orgs = _orgs(ck, _resume(ck))
    if not docs or not orgs:
        ck.skip(name, "hard", "no prose documents" if not docs else "no résumé/profile entries")
        return
    roles = [str(r).lower() for r in cfg["role_nouns"]]
    seniority = {str(s).lower() for s in cfg["seniority_words"]}
    window = cfg["year_window"]
    role_alt = "|".join(re.escape(r) for r in sorted(roles, key=len, reverse=True))
    title_i = r"((?:[A-Za-z][\w/&+.'-]*\s+){0,4}?(?:" + role_alt + r")s?)(?![\w-])"
    title_cap = r"((?:[A-Z][\w/&+.'-]*\s+){0,4}(?:" + "|".join(re.escape(r.capitalize()) for r in roles) + r"))(?![\w-])"
    art = r"(?:(?:an?|the|my)\s+)?"
    mism, unsure = [], []
    for org_low, rec in orgs.items():
        org_rx = r"(?<![A-Za-z0-9])(?i:" + re.escape(rec["name"]) + r")(?![A-Za-z0-9])"
        anchored = [
            re.compile(r"(?i:\b(?:as|am|was|i'm|i’m)\s+)" + art + "(?i:" + title_i + r")\s+(?i:at|with|for)\s+(?:the\s+)?" + org_rx),
            re.compile(org_rx + r"\s*,?\s+(?i:where\s+i\s+(?:am|was|work(?:ed)?\s+as|serve[ds]?\s+as)|as)\s+" + art
                       + "(?i:" + title_i + ")"),
        ]
        loose = re.compile(title_cap + r"\s+(?:at|with)\s+(?:the\s+)?" + org_rx)
        for doc, text, _ in docs:
            if not re.search(org_rx, text):
                continue
            spans = []
            if rec["titles"]:
                for rx in anchored:
                    for m in rx.finditer(text):
                        spans.append(m.span(1))
                        verdict = _compare_title(m.group(1), rec["titles"], seniority)
                        if verdict != "ok":
                            item = {"doc": doc, "org": rec["name"], "found": m.group(1).strip(),
                                    "resume": sorted(rec["titles"])}
                            (mism if verdict == "hard" else unsure).append(item)
                for m in loose.finditer(text):
                    if any(a <= m.start(1) < b or m.start(1) <= a < m.end(1) for a, b in spans):
                        continue
                    if _compare_title(m.group(1), rec["titles"], seniority) != "ok":
                        unsure.append({"doc": doc, "org": rec["name"], "found": m.group(1).strip(),
                                       "resume": sorted(rec["titles"])})
            if rec["degrees"]:
                for sent in _sentences(text):
                    if re.search(org_rx, sent):
                        lv = _degree_levels(sent)
                        if lv and not lv & rec["degrees"]:
                            mism.append({"doc": doc, "org": rec["name"], "found": "/".join(sorted(lv)),
                                         "resume": sorted(rec["degrees"])})
        # years are checked per sentence below (nearest org), not per org
    for doc, text, _ in docs:
        for sent in _sentences(text):
            mentions = []
            for rec in orgs.values():
                org_rx = r"(?<![A-Za-z0-9])" + re.escape(rec["name"]) + r"(?![A-Za-z0-9])"
                mentions += [(m.start(), m.end(), rec) for m in re.finditer(org_rx, sent, re.I)]
            if not mentions:
                continue
            for ym in YEAR_RE.finditer(sent):
                before = TOKEN_RE.findall(sent[:ym.start()])
                if not before or before[-1].lower() not in DATE_WORDS:
                    continue
                y = int(ym.group(1))
                dist, rec = min(((max(s - ym.end(), ym.start() - e, 0), r) for s, e, r in mentions),
                                key=lambda x: x[0])
                if dist > window or not rec["check_years"] or not rec["years"]:
                    continue
                if not any((lo is None or y >= lo) and (hi is None or y <= hi) for lo, hi in rec["years"]):
                    rng = ", ".join(f"{lo or '?'}-{hi or 'present'}" for lo, hi in rec["years"])
                    mism.append({"doc": doc, "org": rec["name"], "found": str(y), "resume": [rng]})
    ex["title_mismatches"], ex["title_uncertain"] = mism, unsure

    def fmt(items: list[dict[str, Any]]) -> str:
        return "; ".join(f"{i['doc']}: {i['org']} '{i['found']}' vs résumé {', '.join(i['resume'])}" for i in items)

    ck.add(name, "hard", not mism,
           f"titles, degrees and years agree with the résumé in {len(docs)} documents" if not mism else fmt(mism))
    if unsure:
        ck.add("employer_title_uncertain", "soft", False, fmt(unsure) + " (check the wording matches the résumé title)")


# --------------------------------------------------------------------------- #
# 3. numbers_consistent
# --------------------------------------------------------------------------- #

def _clauses(sentence: str) -> list[str]:
    return [c for c in CLAUSE_SPLIT.split(sentence) if c.strip()] or [sentence]


def _facts_text(v: Any) -> list[str]:
    out = []
    for f in v if isinstance(v, list) else []:
        if isinstance(f, dict):
            out.append(str(f.get("fact") or ""))
        elif isinstance(f, str):
            out.append(f)
    return out


def _context_values(ck: Any) -> set[float]:
    """Values of numbers in the posting text and every artifact's `facts_used`: company facts, not bullet claims."""
    parts: list[str] = []
    if isinstance(ck.posting, dict):
        parts += [str(ck.posting.get(k) or "") for k in ("title", "description_text")]
    fm = ck.cover_fm if isinstance(ck.cover_fm, dict) else {}
    parts += _facts_text(fm.get("facts_used") or fm.get("company_facts"))
    for a in ck.answers if isinstance(ck.answers, list) else []:
        if isinstance(a, dict):
            parts += _facts_text(a.get("facts_used"))
    for _, _, d in outreach_items(ck):
        parts += _facts_text(d.get("facts_used"))
    data = outreach_data(ck) or {}
    parts += _facts_text(data.get("facts_used"))
    return {p["value"] for p in parse_numbers("\n".join(parts))
            if p["value"] is not None and not p["vague"] and not p["glued"]}


def _check_numbers(ck: Any, ex: dict[str, Any], docs: list[tuple[str, str, set[str]]], cfg: dict[str, Any]) -> None:
    name = "numbers_consistent"
    rj = _resume(ck)
    refs: dict[str, tuple[str, str]] = {}   # bullet id -> (reference text, reference doc)
    for _, e in _resume_entries(rj):
        for b in e.get("bullets") or []:
            if isinstance(b, dict) and b.get("id") and b.get("text"):
                refs[str(b["id"])] = (str(b["text"]), "resume.json")
    all_docs = list(docs)
    if ck.resume_txt is not None:
        all_docs.insert(0, ("resume.txt", ck.resume_txt, set(refs)))
    if not all_docs or not (refs or any(ids for _, _, ids in docs)):
        ck.skip(name, "hard", "no documents with bullet claims to compare")
        return
    min_overlap = cfg["min_overlap"]
    context = _context_values(ck)
    mism, para, n = [], [], 0
    for doc, text, ids in all_docs:
        cands = {}
        for bid in set(ids) | set(refs):
            if bid in refs:
                cands[bid] = refs[bid]
            elif bid in ck.profile.bullets:
                cands[bid] = (str(ck.profile.bullets[bid].get("text") or ""), "profile")
        if not cands:
            continue
        words = {bid: _content(t) for bid, (t, _) in cands.items()}
        for sent in _sentences(text if doc != "resume.txt" else text.replace("\n", "\n\n")):
            sw = _content(sent)
            best, score = None, 0
            for bid in sorted(cands):
                s = len(sw & words[bid])
                if s > score:
                    best, score = bid, s
            if best is None or score < min_overlap:
                continue
            ref_text, ref_doc = cands[best]
            rnums = [r for r in parse_numbers(ref_text) if not r["vague"] and r["value"] is not None]
            if not rnums:
                continue
            n += 1
            # only the clause(s) that restate the bullet: "Your platform ingests 40 million events, and at Acme
            # I built ... 2 million events" compares 2 million, not the company's 40 million
            clause_score = [(len(_content(c) & words[best]), c) for c in _clauses(sent)]
            top = max(sc for sc, _ in clause_score)
            nums = [p for sc, c in clause_score if sc == top for p in parse_numbers(c)]
            for p in nums:
                paired = [r for r in rnums if _paired(p, r)]
                if not paired:
                    continue
                refs_s = ", ".join(r["raw"] for r in paired)
                item = {"doc": doc, "id": best, "found": p["raw"], "expected": refs_s, "reference": ref_doc}
                if p["vague"]:
                    para.append(item)
                    continue
                equal = [r for r in paired if abs(r["value"] - p["value"]) < 1e-9]
                if equal:
                    # hedging is a paraphrase only when the bullet states the number exactly; a bullet that
                    # itself says "about 2 months" (or "~2") may be restated with a hedge
                    if p["hedged"] and not any(_same_hedge(p, r) for r in equal):
                        para.append(item)
                elif p["hedged"] and any(r["estimate"] for r in paired):
                    continue
                elif p["value"] is not None and any(abs(p["value"] - v) < 1e-9 for v in context):
                    continue  # a number the posting / facts_used states: a company fact, not the bullet's
                else:
                    mism.append(item)
    ex["number_mismatches"], ex["number_paraphrases"] = mism, para

    def fmt(items: list[dict[str, Any]]) -> str:
        return "; ".join(f"{i['doc']}: {i['id']} says '{i['found']}' but {i['reference']} says '{i['expected']}'"
                         for i in items)

    ck.add(name, "hard", not mism, f"{n} bullet claims restated with the same numbers" if not mism else fmt(mism))
    if para:
        ck.add("numbers_paraphrased", "soft", False, fmt(para) + " (state the bullet's exact number)")


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #

def _config(ck: Any) -> dict[str, Any]:
    raw = ck.qa_cfg.get("consistency") if isinstance(ck.qa_cfg, dict) else None
    raw = raw if isinstance(raw, dict) else {}

    def num(key: str, default: int) -> int:
        try:
            return int(raw.get(key, default))
        except (TypeError, ValueError):
            return default

    def lst(key: str, default: tuple[str, ...]) -> list[str]:
        v = raw.get(key)
        return [str(x) for x in v] if isinstance(v, list) and v else list(default)

    return {"enabled": raw.get("enabled", True) is not False, "min_overlap": num("min_overlap", DEFAULT_MIN_OVERLAP),
            "year_window": num("year_window", DEFAULT_YEAR_WINDOW),
            "role_nouns": lst("role_nouns", DEFAULT_ROLE_NOUNS),
            "seniority_words": lst("seniority_words", DEFAULT_SENIORITY_WORDS)}


def check_cross_doc(ck: Any) -> None:
    """Add the cross-document consistency checks to `ck` (a careeros.qa.Checker)."""
    cfg = _config(ck)
    docs = prose_docs(ck)
    ex: dict[str, Any] = {
        "docs": (["resume.json"] if _resume(ck) is not None else []) + (["resume.txt"] if ck.resume_txt is not None else [])
        + [d for d, _, _ in docs],
        "config": {k: cfg[k] for k in ("enabled", "min_overlap", "year_window")},
        "letter_off_resume": [], "title_mismatches": [], "title_uncertain": [],
        "number_mismatches": [], "number_paraphrases": [],
    }
    ck.extras["consistency"] = ex
    if not cfg["enabled"]:
        for c in CHECKS:
            ck.skip(c, "soft" if c == "letter_experiences_on_resume" else "hard", "consistency.enabled is false")
        return
    _check_letter_entries(ck, ex)
    _check_titles(ck, ex, docs, cfg)
    _check_numbers(ck, ex, docs, cfg)
