"""Match application-form questions to profile/standard_answers.yaml, and classify the rest.

    from careeros.apply.questions import match_standard_answer, classify_question

    hit = match_standard_answer("Are you legally authorized to work in the US?", "profile/standard_answers.yaml")
    # -> ("work_authorization", "Yes")   or None
    classify_question("Why do you want to work at Acme?")   # -> "essay"

Rules (config/targets.yaml safety.pause_on):
- A match whose answer is null (salary_expectation) is returned as (key, None): the caller must raise an
  Action Item, never guess.
- EEO questions are never matched to the standard list; the skill fills them only from the `eeo:` block
  via `select_eeo_option(field, offered_option_labels, load_eeo_answers(path))`.
- Standard entries are tried in file order; first hit wins, so specific patterns go above general ones.
- `sensitive` (SSN, date of birth, bank, passport, driver's license, fees; careeros.safety.scam) is never
  answered: the scam gate stops the run (`careeros safety fields`).
- Address minimization: use `answer_for(label, yaml, required=...)`. An optional street field stays blank;
  a required one gets the street entry (or the `full` form of `address`).
- Anything classified `unknown` or `essay` goes to the answer-question skill; `legal`/`salary` with no
  standard match become Action Items.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

QuestionKind = Literal["sensitive", "standard", "eeo", "essay", "salary", "legal", "unknown"]

# Order matters: eeo and salary are checked before the generic standard list so that a form label like
# "Gender" is never matched by a loose standard pattern, and "Expected salary" is always paused.
_EEO_RE = re.compile(
    r"\b(gender|race|ethnicity|ethnic|hispanic|latino|veteran|disability|disabilit|"
    r"self.?identif|eeoc?|equal (employment )?opportunity|sexual orientation|transgender|"
    r"protected (veteran|class)|voluntary)\b",
    re.I,
)
_SALARY_RE = re.compile(
    r"\b(salary|compensation|desired pay|expected pay|pay expectation|base pay|hourly rate|"
    r"rate expectation|comp expectation|wage)\b",
    re.I,
)
_LEGAL_RE = re.compile(
    r"\b(authori[sz]ed to work|work authori[sz]ation|sponsorship|visa|immigration|citizen|"
    r"non.?compete|restrictive covenant|clearance|background check|criminal|convicted|felony|"
    r"18 years|legal age|at least 18|eligible to work|export control|itar)\b",
    re.I,
)
_ESSAY_RE = re.compile(
    r"\b(why (do you want|are you interested|us|this role|acme)|tell us|describe|explain|"
    r"what (interests|excites|draws) you|in your own words|cover letter|anything else|"
    r"additional information|what would you|how would you|share (an|a|your)|walk us through)\b",
    re.I,
)
_STANDARD_HINT_RE = re.compile(
    r"\b(linkedin|github|portfolio|website|phone|email|start date|availability|available|"
    r"current (employer|company|title|role)|years of|how did you hear|referr|previously applied|"
    r"applied before|relocat|hybrid|on.?site|in.?office|remote|degree|education|school|"
    r"university|college|major|field of study|graduat|gpa|pronouns|address|city|zip|postal)\b",
    re.I,
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


_EEO_SPLIT_RE = re.compile(r"^eeo:\s*(#.*)?$", re.M)


@lru_cache(maxsize=8)
def _load_answers(path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Accepts three shapes:
    1. dict: {answers: [...], eeo: {...}}
    2. list: [{key,...}, ...]  (no eeo block)
    3. list followed by a top-level `eeo:` mapping (the shipped profile/standard_answers.yaml). That is
       not valid YAML as one document, so the text is split at the `eeo:` line and parsed as two.
    """
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        m = _EEO_SPLIT_RE.search(text)
        if not m:
            raise
        head = yaml.safe_load(text[: m.start()]) or []
        tail = yaml.safe_load(text[m.start():]) or {}
        data = {"answers": head, "eeo": tail.get("eeo") or {}}
    if isinstance(data, dict):
        items = data.get("answers")
        if not isinstance(items, list):
            items = next((v for v in data.values() if isinstance(v, list)), [])
        eeo = data.get("eeo") or {}
    else:
        items = [x for x in (data or []) if isinstance(x, dict) and "key" in x]
        eeo = {}
    return [x for x in items if isinstance(x, dict) and "key" in x], eeo


def load_standard_answers(path: str | Path) -> list[dict[str, Any]]:
    """The list of {key, match: [regex], answer, note?} entries."""
    return _load_answers(str(path))[0]


def load_eeo_answers(path: str | Path) -> dict[str, Any]:
    """The `eeo:` block. The skill fills EEO fields only from these exact values."""
    return _load_answers(str(path))[1]


def classify_question(text: str, standard_answers_yaml: str | Path | None = None) -> QuestionKind:
    """Rough bucket for a form label. `standard` when it would hit the standard list."""
    t = _norm(text)
    if not t:
        return "unknown"
    if _is_sensitive(t):
        return "sensitive"
    if _EEO_RE.search(t):
        return "eeo"
    if _SALARY_RE.search(t):
        return "salary"
    if _LEGAL_RE.search(t):
        return "legal"
    if standard_answers_yaml is not None and match_standard_answer(t, standard_answers_yaml) is not None:
        return "standard"
    if _ESSAY_RE.search(t) or len(t.split()) >= 12:
        return "essay"
    if _STANDARD_HINT_RE.search(t):
        return "standard"
    return "unknown"


def match_standard_answer(question_text: str, standard_answers_yaml: str | Path) -> tuple[str, Any] | None:
    """Return (key, answer) for the first standard entry (in file order) whose `match` regex hits.

    File order is the priority order: put specific entries (`years_experience_fulltime`) above general
    ones (`years_experience`). EEO questions never match. Salary matches return (key, None) because
    the answer is null in the YAML; the caller must open an Action Item.
    """
    t = _norm(question_text)
    if not t or _EEO_RE.search(t) or _is_sensitive(t):
        return None
    # A legal or salary question may only be answered by an entry whose pattern hit the legal/salary
    # wording itself: "convicted of a crime in any city" must not borrow the `address` answer.
    guard_spans = [m.span() for rx in (_SALARY_RE, _LEGAL_RE) for m in rx.finditer(t)]
    for entry in load_standard_answers(standard_answers_yaml):
        for pat in entry.get("match") or []:
            try:
                m = re.search(pat, t, re.I)
            except re.error:
                continue
            if not m:
                continue
            if guard_spans and not any(m.start() < e and s < m.end() for s, e in guard_spans):
                continue
            return entry["key"], entry.get("answer")
    return None


_STREET_RE = re.compile(r"\b(street|address line ?1|address 1|mailing address|home address)\b", re.I)


def _is_sensitive(text: str) -> bool:
    from careeros.safety.scam import check_form_fields

    return bool(check_form_fields([text]))


def answer_for(label: str, standard_answers_yaml: str | Path, required: bool = False) -> tuple[str, Any] | None:
    """`match_standard_answer` plus data minimization. A street-address field is left blank (None) unless
    the form marks it required; then the first standard hit is used, with an `address` entry's `full`
    value preferred over its city form. Sensitive fields are never answered."""
    t = _norm(label)
    if _is_sensitive(t):
        return None
    if _STREET_RE.search(t):
        if not required:
            return None
        for entry in load_standard_answers(standard_answers_yaml):
            if entry.get("key") == "address" and entry.get("full"):
                hit = match_standard_answer(t, standard_answers_yaml)
                if hit and hit[0] == "address":
                    return "address", entry["full"]
    return match_standard_answer(t, standard_answers_yaml)


# --- EEO ---------------------------------------------------------------------------------------------

def normalize_eeo(eeo: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Accept both `field: "value"` and `field: {answer, prefer?, match_not?}`; return the dict shape."""
    out: dict[str, dict[str, Any]] = {}
    for field, v in (eeo or {}).items():
        if isinstance(v, dict):
            out[field] = {
                "answer": v.get("answer"),
                "prefer": v.get("prefer"),
                "match_not": [str(x) for x in (v.get("match_not") or [])],
            }
        else:
            out[field] = {"answer": v, "prefer": None, "match_not": []}
    return out


def _label_matches(option: str, wanted: str) -> Literal["exact", "prefix", "substring", None]:
    """Whole-word comparison: "Male" never matches inside "Female", "No" never prefixes "Not Declared"."""
    o, w = _norm(option).lower(), _norm(wanted).lower()
    if not o or not w:
        return None
    if o == w:
        return "exact"
    m = re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", o)
    if m is None:
        return None
    return "prefix" if m.start() == 0 else "substring"


def select_eeo_option(field: str, options: list[str], eeo: dict[str, Any]) -> str | None:
    """Pick the option label the form offers for one EEO field, or None (leave blank).

    Ranking: `prefer` beats `answer`; within each, exact label > word-prefix > whole-word substring
    ("Male" never matches inside "Female"). A prefix match
    is always allowed. A substring-only match is dropped when the option contains a `match_not` term,
    so "White (Not Hispanic or Latino)" still wins for answer "White" (prefix) while a stray
    "Hispanic or Latino, White descent" style option would not.
    """
    spec = normalize_eeo(eeo).get(field)
    if not spec or not options:
        return None
    match_not = [m.lower() for m in spec["match_not"]]
    for wanted in (spec["prefer"], spec["answer"]):
        if not wanted:
            continue
        exact_hits: list[str] = []
        prefix_hits: list[str] = []
        sub_hits: list[str] = []
        for opt in options:
            kind = _label_matches(opt, str(wanted))
            if kind == "exact":
                exact_hits.append(opt)
            elif kind == "prefix":
                prefix_hits.append(opt)
            elif kind == "substring" and not any(mn in opt.lower() for mn in match_not):
                sub_hits.append(opt)
        for hits in (exact_hits, prefix_hits, sub_hits):
            if hits:
                return hits[0]
    return None


def clear_cache() -> None:
    _load_answers.cache_clear()
