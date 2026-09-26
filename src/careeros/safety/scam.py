"""Scam / data-harvesting checks. Pure functions: they read a Posting and Settings and return flags.

Hard flags stop the pipeline (Action Item `scam_suspected`, status needs_review, never auto). Soft flags
lower fit and ask for review. Rules (TODO.md "Safety"):
- apply URL must be on the company's own domain or a known ATS
- no free-provider recruiter email, no scam phrases (WhatsApp/Telegram interviews, check deposits,
  equipment you buy and get reimbursed for, fees, pay in crypto or gift cards)
- no form field asking for identity documents or bank details before an offer, and never a fee
- salary far above market is soft
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import urlparse

from careeros.config import Settings, normalize_company
from careeros.models import Posting

Severity = Literal["hard", "soft"]


@dataclass(frozen=True)
class Flag:
    code: str
    severity: Severity
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Flag":
        return cls(str(d["code"]), d["severity"], str(d.get("detail") or ""))


# Registrable domain per ATS family (see src/careeros/apply/adapters.md). A posting whose apply URL is on
# one of these is on a real application system, whatever company it names.
ATS_DOMAINS: dict[str, tuple[str, ...]] = {
    "greenhouse": ("greenhouse.io",),
    "lever": ("lever.co",),
    "ashby": ("ashbyhq.com",),
    "workday": ("myworkdayjobs.com", "myworkdaysite.com", "workday.com"),
    "icims": ("icims.com",),
    "smartrecruiters": ("smartrecruiters.com",),
    "bamboohr": ("bamboohr.com",),
    "jobvite": ("jobvite.com",),
    "taleo": ("taleo.net",),
    "successfactors": ("successfactors.com", "successfactors.eu", "sapsf.com"),
    "workable": ("workable.com",),
    "rippling": ("rippling.com", "rippling-ats.com"),
    "gem": ("gem.com",),
    "dover": ("dover.com", "dover.io"),
}
KNOWN_ATS_DOMAINS: frozenset[str] = frozenset(d for ds in ATS_DOMAINS.values() for d in ds)

# Postings found on these must be resolved to the company's board or careers page before auto-submit.
AGGREGATORS: frozenset[str] = frozenset({"jobright", "handshake", "linkedin", "indeed", "glassdoor", "ziprecruiter",
                                          "simplify", "wellfound"})

AGGREGATOR_DOMAINS: frozenset[str] = frozenset({"jobright.ai", "joinhandshake.com", "linkedin.com", "indeed.com",
                                                 "glassdoor.com", "ziprecruiter.com", "simplify.jobs", "wellfound.com"})

FREE_EMAIL_DOMAINS: frozenset[str] = frozenset({
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com", "yahoo.com", "ymail.com",
    "icloud.com", "me.com", "aol.com", "proton.me", "protonmail.com", "gmx.com", "mail.com", "zoho.com", "yandex.com",
})

_TWO_LEVEL_SUFFIXES = {"co.uk", "ac.uk", "org.uk", "com.au", "co.in", "co.jp", "com.br", "co.nz", "com.sg", "com.mx"}
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")

SCAM_PHRASES: list[tuple[str, re.Pattern[str]]] = [
    ("messaging-app interview", re.compile(
        r"\b(whats\s?app|telegram|signal app|google hangouts?|wickr)\b.{0,60}\b(interview|contact|message|chat|reach)"
        r"|\b(interview|contact|message|chat|reach)\w*\b.{0,60}\b(whats\s?app|telegram|wickr)\b", re.I | re.S)),
    ("check deposit", re.compile(r"\b(deposit|cash)\b.{0,30}\b(a|the|this) (check|cheque)\b"
                                 r"|\b(check|cheque)s?\b.{0,20}\bto (deposit|cash)\b", re.I | re.S)),
    ("buy equipment, get reimbursed", re.compile(
        r"\b(purchase|buy)\b.{0,60}\b(equipment|laptop|software|supplies)\b.{0,80}\breimburs", re.I | re.S)),
    ("fee to apply or train", re.compile(
        r"\b(application|training|registration|onboarding|processing|placement|background.check|starter kit)\s+fee\b"
        r"|\bpay\b.{0,20}\bto (apply|start|be considered)\b", re.I | re.S)),
    ("paid in crypto or gift cards", re.compile(
        r"\b(paid|payment|salary|compensation)\b.{0,30}\b(crypto(currency)?|bitcoin|btc|usdt|tether|gift cards?)\b", re.I | re.S)),
    ("no interview, hired immediately", re.compile(r"\bno interview (required|needed)\b|\bhired (immediately|on the spot)\b", re.I)),
]

# Form fields that must never be filled before an offer. Fees are refused at any stage.
_FEE_FIELD_RE = re.compile(r"\b(application|training|processing|registration|onboarding)?\s*fee\b|\bpayment (method|details)\b",
                           re.I)
SENSITIVE_FIELD_RE = re.compile(
    r"\b(ssn|social security|social insurance|national (id|identity|insurance)|tax (id|identification)|\bitin\b|"
    r"date of birth|birth ?date|\bdob\b|place of birth|bank (account|name|details)|account number|routing (number|#)|"
    r"\biban\b|swift|sort code|credit card|debit card|card number|cvv|passport|driver'?s? licen[cs]e|"
    r"state id|government.?(issued )?id|photo id|id (card|upload|document)|mother'?s maiden)\b",
    re.I,
)


def registrable_domain(url: str) -> str:
    """`https://acme.wd5.myworkdayjobs.com/x` -> `myworkdayjobs.com`; `careers.acme.co.uk` -> `acme.co.uk`."""
    u = (url or "").strip()
    if not u:
        return ""
    host = urlparse(u if "//" in u else "//" + u).hostname or ""
    parts = [p for p in host.lower().split(".") if p]
    if len(parts) <= 2:
        return ".".join(parts)
    last2 = ".".join(parts[-2:])
    return ".".join(parts[-3:]) if last2 in _TWO_LEVEL_SUFFIXES else last2


def company_domains(settings: Settings, company: str) -> set[str]:
    """Domains configured for a company: `companies.yaml: company_domains {Company: domain | [domains]}` and
    `boards[].domain`. Empty when unknown (then the name-in-domain heuristic applies)."""
    key = normalize_company(company)
    out: set[str] = set()
    for name, doms in (settings.companies.get("company_domains") or {}).items():
        if normalize_company(str(name)) == key:
            for d in doms if isinstance(doms, list) else [doms]:
                out.add(registrable_domain(str(d)))
    for b in settings.boards:
        if b.get("domain") and normalize_company(str(b.get("company", ""))) == key:
            out.add(registrable_domain(str(b["domain"])))
    return {d for d in out if d}


_TRUSTED_TLDS = {"com", "io", "co", "ai", "org", "net", "dev", "tech", "us", "app", "inc", "jobs", "careers"}


def _name_in_domain(company: str, domain: str) -> bool:
    """`Acme Corp` owns `acme.com` / `acmecorp.io`. Strict on purpose: the label must equal the squashed
    name (or its first word, 4+ letters) on a mainstream TLD, so look-alikes such as `acme-careers.xyz`
    or `acmehiring.com` fail and need `company_domains` in companies.yaml."""
    label, _, tld = domain.partition(".")
    words = normalize_company(company).split()
    if not label or not words or tld.split(".")[-1] not in _TRUSTED_TLDS:
        return False
    return label == "".join(words) or (len(words[0]) >= 4 and label == words[0])


def is_company_or_ats_domain(url: str, company: str, settings: Settings) -> bool:
    dom = registrable_domain(url)
    if not dom:
        return False
    if dom in KNOWN_ATS_DOMAINS or dom in company_domains(settings, company):
        return True
    return not company_domains(settings, company) and _name_in_domain(company, dom)


def _curated_names(settings: Settings) -> list[str]:
    tiers = settings.prestige_tiers
    names = [str(b.get("company", "")) for b in settings.boards]
    names += settings.merged_dream_list()
    names += [str(n) for t, ns in tiers.items() if t != "avoid" for n in ns]
    names += [str(n) for n in (settings.companies.get("company_domains") or {})]
    return [n for n in names if n]


def company_trust(settings: Settings, company: str, verified: list[dict[str, Any]] | None = None) -> str:
    """`curated` (on a board, the dream list, a prestige tier or company_domains), `verified` (in
    data/verified_companies.yaml), else `unverified`: could be a made-up company."""
    from careeros.config import _fuzzy_eq

    key = normalize_company(company)
    if key and any(_fuzzy_eq(key, normalize_company(n)) for n in _curated_names(settings)):
        return "curated"
    if key and any(normalize_company(str(v.get("company") or "")) == key for v in verified or []):
        return "verified"
    return "unverified"


def _lookalike_of(settings: Settings, company: str, apply_url: str) -> str | None:
    """A non-curated name that contains a curated brand ("Stripe Talent Recruiting") while the apply URL is
    neither a known ATS nor that brand's own domain: the classic impersonation scam."""
    key = normalize_company(company)
    dom = registrable_domain(apply_url)
    for brand in _curated_names(settings):
        b = normalize_company(brand)
        if len(b) < 4 or b == key or not re.search(r"(?<![a-z0-9])" + re.escape(b) + r"(?![a-z0-9])", key):
            continue
        if dom in KNOWN_ATS_DOMAINS or dom in company_domains(settings, brand) or _name_in_domain(brand, dom):
            continue
        return brand
    return None


def _posting_emails(p: Posting) -> list[str]:
    text = " ".join([p.description_text or "", str(p.raw.get("contact_email") or ""),
                     str(p.raw.get("recruiter_email") or "")])
    return [m.group(0) for m in _EMAIL_RE.finditer(text)]


def check_posting(p: Posting, settings: Settings, registry: list[dict[str, Any]] | None = None,
                  verified: list[dict[str, Any]] | None = None) -> list[Flag]:
    """All posting-level checks. `registry` / `verified` are the loaded `data/flagged_registry.yaml` and
    `data/verified_companies.yaml` entries."""
    from careeros.safety.registry import is_flagged

    flags: list[Flag] = []
    apply_url = p.apply_url or p.url
    hit = is_flagged(registry or [], p.company, apply_url)
    if hit:
        flags.append(Flag("registry", "hard", f"in flagged registry: {hit.get('reason') or 'flagged'}"))
    trust = company_trust(settings, p.company, verified)
    brand = _lookalike_of(settings, p.company, apply_url) if trust == "unverified" else None
    if brand:
        flags.append(Flag("lookalike_company", "hard",
                          f"\"{p.company}\" borrows the name {brand} but applies on {registrable_domain(apply_url) or '?'}"))
    elif trust == "unverified":
        flags.append(Flag("company_unverified", "soft",
                          f"{p.company} is not on your boards, dream list or tiers; verify it is real "
                          "(official site lists the role, LinkedIn page with real employees), then "
                          "`careeros safety verify`"))
    if apply_url and not is_company_or_ats_domain(apply_url, p.company, settings):
        flags.append(Flag("apply_domain", "hard",
                          f"{registrable_domain(apply_url)} is neither {p.company}'s domain nor a known ATS "
                          "(add it to companies.yaml: company_domains if it is theirs)"))
    for email in _posting_emails(p):
        dom = email.rsplit("@", 1)[1].lower()
        if dom in FREE_EMAIL_DOMAINS:
            flags.append(Flag("free_email_contact", "hard", f"recruiter contact on a free provider: {email}"))
            break
    text = " ".join([p.title or "", p.description_text or ""])
    for label, rx in SCAM_PHRASES:
        m = rx.search(text)
        if m:
            flags.append(Flag("scam_phrase", "hard", f"{label}: \"{m.group(0)[:80]}\""))
    floor = (settings.targets.get("candidate") or {}).get("min_base_usd")
    mult = float(((settings.targets.get("safety") or {}).get("scam") or {}).get("salary_max_multiple", 3))
    top = p.salary_max or p.salary_min
    if floor and top and (p.salary_currency or "USD").upper() == "USD" and top > float(floor) * mult:
        flags.append(Flag("salary_implausible", "soft", f"salary {int(top):,} is over {mult:g}x your floor {int(floor):,}"))
    return flags


def check_form_fields(labels: list[str], status: str | None = None) -> list[Flag]:
    """Visible form labels/placeholders/upload prompts -> hard flags. Identity and bank fields are allowed
    only once the job status is `offer` (onboarding paperwork); a fee is refused at any stage."""
    flags: list[Flag] = []
    for label in labels:
        t = " ".join(str(label or "").split())
        if not t:
            continue
        if _FEE_FIELD_RE.search(t) and not re.search(r"\bfee(s)?[- ]free\b", t, re.I):
            flags.append(Flag("sensitive_field", "hard", f"asks for a fee or payment: {t}"))
        elif SENSITIVE_FIELD_RE.search(t) and status != "offer":
            flags.append(Flag("sensitive_field", "hard", f"asks for identity or bank data before an offer: {t}"))
    return flags


def auto_submit_allowed(p: Posting, settings: Settings) -> tuple[bool, str]:
    """(True, "") only for an allowlisted ATS reached on its own domain (or the company's), from the
    company's board. Aggregator postings need `raw.resolved_from` (set once resolved to the real board)."""
    safety = settings.targets.get("safety") or {}
    allowed = [str(a).lower() for a in safety.get("auto_submit_ats") or []]
    ats = (p.ats or "").lower()
    if ats not in allowed:
        return False, f"ats {ats or '?'} is not in safety.auto_submit_ats"
    apply_url = p.apply_url or p.url
    dom = registrable_domain(apply_url)
    if dom not in ATS_DOMAINS.get(ats, ()) and dom not in company_domains(settings, p.company):
        return False, f"apply domain {dom or '?'} is not {ats}'s or the company's"
    source = str(p.raw.get("source") or "").lower()
    if source in AGGREGATORS and not p.raw.get("resolved_from"):
        return False, f"found on aggregator {source}; resolve to the company's board first"
    return True, ""


def hard(flags: list[Flag]) -> list[Flag]:
    return [f for f in flags if f.severity == "hard"]
