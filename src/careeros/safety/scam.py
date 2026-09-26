"""Scam / data-harvesting checks. Pure functions: they read a Posting and Settings and return flags.

Every flag has a reason code (`SCAM_*`, `COMPANY_*`, `FIELD_*`; ghost checks add `GHOST_*`), a level and an
evidence trail (URLs + timestamp). `verdict(flags)` gives the decision:

    pass    normal: can auto-submit
    review  uncertain or conflicting evidence: a human approves before anything is submitted
    block   strong fraud / privacy violation: never submit (ghost checks may also `skip` a dead posting)
    info    lowers confidence only (fit), never changes the verdict

Only strong signals block: payment/gift cards/crypto/check deposits/buying equipment, remote-access
requests, identity or bank data before an offer, credentials, brand impersonation, and a company whose
name, site, recruiter and posting contradict each other. Weak or single signals (unfamiliar domain,
free-provider recruiter email, chat-app interviews, a company nobody has checked yet) ask for review.
Company priority (dream list) never softens a fraud signal.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlparse

from careeros.config import Settings, _fuzzy_eq, normalize_company
from careeros.models import Posting, now_iso

Level = Literal["block", "skip", "review", "info"]
Verdict = Literal["block", "skip", "review", "pass"]
_RANK = {"block": 3, "skip": 2, "review": 1, "info": 0}


@dataclass(frozen=True)
class Flag:
    code: str
    level: Level
    detail: str = ""
    evidence: tuple[str, ...] = ()
    at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "level": self.level, "detail": self.detail, "evidence": list(self.evidence),
                "at": self.at}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Flag":
        return cls(str(d["code"]), d["level"], str(d.get("detail") or ""), tuple(d.get("evidence") or ()),
                   str(d.get("at") or now_iso()))


def apply_levels(flags: list[Flag], settings: Settings) -> list[Flag]:
    """Per-code level overrides from `targets.yaml: safety.levels` ({CODE: block|skip|review|info|off}),
    so a template user can make e.g. SCAM_FREE_EMAIL_RECRUITER a block, or GHOST_OLD_POST off."""
    over = {str(k).upper(): str(v).lower() for k, v in
            (((settings.targets.get("safety") or {}).get("levels")) or {}).items()}
    out: list[Flag] = []
    for f in flags:
        lv = over.get(f.code)
        if lv == "off":
            continue
        out.append(Flag(f.code, lv, f.detail, f.evidence, f.at) if lv in _RANK else f)  # type: ignore[arg-type]
    return out


def verdict(flags: list[Flag]) -> Verdict:
    top = max((_RANK[f.level] for f in flags), default=0)
    return {3: "block", 2: "skip", 1: "review", 0: "pass"}[top]  # type: ignore[return-value]


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

# (code, level, label, pattern) over the posting title + description.
POSTING_PATTERNS: list[tuple[str, Level, str, re.Pattern[str]]] = [
    ("SCAM_PAYMENT_REQUEST", "block", "fee to apply or train", re.compile(
        r"\b(application|training|registration|onboarding|processing|placement|background.check|starter kit)\s+fee\b"
        r"|\bpay\b.{0,20}\bto (apply|start|be considered)\b", re.I | re.S)),
    ("SCAM_PAYMENT_REQUEST", "block", "gift cards", re.compile(r"\b(purchase|buy|send)\b.{0,30}\bgift ?cards?\b", re.I | re.S)),
    ("SCAM_PAYMENT_REQUEST", "block", "paid in crypto or gift cards", re.compile(
        r"\b(paid|payment|salary|compensation)\b.{0,30}\b(crypto(currency)?|bitcoin|btc|usdt|tether|gift cards?)\b",
        re.I | re.S)),
    ("SCAM_PAYMENT_REQUEST", "block", "check deposit", re.compile(
        r"\b(deposit|cash)\b.{0,30}\b(a|the|this) (check|cheque)\b|\b(check|cheque)s?\b.{0,20}\bto (deposit|cash)\b",
        re.I | re.S)),
    ("SCAM_PAYMENT_REQUEST", "block", "buy equipment, get reimbursed", re.compile(
        r"\b(purchase|buy)\b.{0,60}\b(equipment|laptop|software|supplies)\b.{0,80}\b(reimburs|vendor)", re.I | re.S)),
    ("SCAM_REMOTE_ACCESS_REQUEST", "block", "remote-access software", re.compile(
        r"\b(install|download|run|grant|give)\b.{0,40}\b(anydesk|teamviewer|ultraviewer|rustdesk|remote (desktop|access))\b"
        r"|\b(anydesk|teamviewer|ultraviewer|rustdesk)\s+(id|code)\b", re.I | re.S)),
    ("SCAM_CHAT_ONLY_INTERVIEW", "review", "chat-app interview", re.compile(
        r"\b(whats\s?app|telegram|signal app|google hangouts?|wickr)\b.{0,60}\b(interview|contact|message|chat|reach)"
        r"|\b(interview|contact|message|chat|reach)\w*\b.{0,60}\b(whats\s?app|telegram|wickr)\b", re.I | re.S)),
    ("SCAM_NO_INTERVIEW", "review", "no interview, hired immediately", re.compile(
        r"\bno interview (required|needed)\b|\bhired (immediately|on the spot)\b", re.I)),
]

# Form fields. Remote access, payment and credentials for other accounts block at any stage; identity and
# bank data block before an offer (onboarding paperwork after an offer is normal). Creating a password or
# entering an emailed code on the ATS's own domain is normal account creation.
_REMOTE_FIELD_RE = re.compile(r"\b(anydesk|teamviewer|ultraviewer|rustdesk|remote (access|desktop|control))\b", re.I)
_PAYMENT_FIELD_RE = re.compile(
    r"\b(application|training|processing|registration|onboarding)?\s*fee\b|\bpayment (method|details|info)\b|"
    r"\b(credit|debit) card\b|\bcard number\b|\bcvv\b|\bgift ?card\b|\bcrypto wallet\b", re.I)
_CREDENTIAL_FIELD_RE = re.compile(
    r"\bpass(word|code|phrase)\b|\bsecurity (question|answer)\b|\b(verification|one.time|authentication|auth|2fa|mfa|otp)\s*code\b|"
    r"\b\d.digit code\b|\bcode (we|that we) (sent|texted|emailed)\b|\botp\b", re.I)
_OTHER_ACCOUNT_RE = re.compile(
    r"\b(gmail|outlook|hotmail|yahoo|icloud|apple id|google|email|e-mail|bank(ing)?|linkedin|facebook)\s+"
    r"(account\s+)?(password|passcode|login|pin|security)\b"
    r"|\b(password|passcode|login)\s+(for|to|of)\s+your\s+(gmail|email|e-mail|bank|linkedin|apple id|google)", re.I)
SENSITIVE_FIELD_RE = re.compile(
    r"\b(ssn|social security|social insurance|national (id|identity|insurance)|tax (id|identification)|\bitin\b|"
    r"date of birth|birth ?date|\bdob\b|place of birth|bank (account|name|details)|account number|routing (number|#)|"
    r"\biban\b|swift|sort code|passport|driver'?s? licen[cs]e|state id|government.?(issued )?id|photo id|"
    r"id (card|upload|document)|mother'?s maiden)\b",
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


def company_risk(settings: Settings, company: str,
                 verified: list[dict[str, Any]] | None = None) -> tuple[str, dict[str, Any] | None]:
    """(`curated` | `low` | `medium` | `high` | `unchecked`, verified entry). Curated = on a board, the dream
    list, a prestige tier or company_domains. Otherwise the latest `careeros safety verify` record decides;
    a company nobody has checked yet is `unchecked` (review), never suspicious by itself."""
    key = normalize_company(company)
    if key and any(_fuzzy_eq(key, normalize_company(n)) for n in _curated_names(settings)):
        return "curated", None
    for v in verified or []:
        if key and normalize_company(str(v.get("company") or "")) == key:
            return str(v.get("risk") or "medium"), v
    return "unchecked", None


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


def _ev(*urls: Any) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(u) for u in urls if u))


def check_posting(p: Posting, settings: Settings, registry: list[dict[str, Any]] | None = None,
                  verified: list[dict[str, Any]] | None = None) -> list[Flag]:
    """All posting-level checks. `registry` / `verified` are the loaded `data/flagged_registry.yaml` and
    `data/verified_companies.yaml` entries."""
    from careeros.safety.registry import is_flagged

    flags: list[Flag] = []
    apply_url = p.apply_url or p.url
    src = _ev(p.url, apply_url if apply_url != p.url else None)

    hit = is_flagged(registry or [], p.company, apply_url)
    if hit:
        level: Level = "block" if hit.get("confidence", "high") == "high" else "review"
        flags.append(Flag("SCAM_FLAGGED_BEFORE", level,
                          f"flagged before ({hit.get('confidence', 'high')} confidence): {hit.get('reason') or '?'}",
                          _ev(*(hit.get("evidence") or []))))

    risk, entry = company_risk(settings, p.company, verified)
    brand = _lookalike_of(settings, p.company, apply_url) if risk not in ("curated", "low") else None
    if brand:
        flags.append(Flag("SCAM_BRAND_DOMAIN_MISMATCH", "block",
                          f"\"{p.company}\" uses the name {brand} but applies on {registrable_domain(apply_url) or '?'}",
                          src))
    ev = _ev(*((entry or {}).get("evidence") or [])) or src
    if risk == "unchecked":
        flags.append(Flag("COMPANY_NOT_YET_CHECKED", "review",
                          f"{p.company} is not on your boards, dream list or tiers and has not been checked yet "
                          "(unknown is not suspicious: /score-job verifies it)", src))
    elif risk == "medium":
        flags.append(Flag("COMPANY_SPARSE_PUBLIC_FOOTPRINT", "review",
                          f"{p.company}: little public information; " + "; ".join((entry or {}).get("signals") or []), ev))
    elif risk == "high":
        flags.append(Flag("COMPANY_CONTRADICTIONS", "block",
                          f"{p.company}: " + "; ".join((entry or {}).get("signals") or ["contradictory evidence"]), ev))

    if apply_url and not is_company_or_ats_domain(apply_url, p.company, settings):
        flags.append(Flag("SCAM_APPLY_DOMAIN_UNRECOGNIZED", "review",
                          f"{registrable_domain(apply_url)} is neither {p.company}'s known domain nor a known ATS "
                          "(add it to companies.yaml: company_domains if it is theirs)", src))
    for email in _posting_emails(p):
        if email.rsplit("@", 1)[1].lower() in FREE_EMAIL_DOMAINS:
            flags.append(Flag("SCAM_FREE_EMAIL_RECRUITER", "review",
                              f"recruiter contact on a free provider: {email} (agencies and founders do this too)", src))
            break
    text = " ".join([p.title or "", p.description_text or ""])
    for code, level, label, rx in POSTING_PATTERNS:
        m = rx.search(text)
        if m:
            flags.append(Flag(code, level, f"{label}: \"{m.group(0)[:80]}\"", src))

    floor = (settings.targets.get("candidate") or {}).get("min_base_usd")
    mult = float(((settings.targets.get("safety") or {}).get("scam") or {}).get("salary_max_multiple", 3))
    top = p.salary_max or p.salary_min
    if floor and top and (p.salary_currency or "USD").upper() == "USD" and top > float(floor) * mult:
        flags.append(Flag("SCAM_SALARY_IMPLAUSIBLE", "review",
                          f"salary {int(top):,} is over {mult:g}x your floor {int(floor):,}", src))
    # one flag per code+level keeps the trail readable (several payment phrases -> one SCAM_PAYMENT_REQUEST)
    seen: set[tuple[str, str]] = set()
    out: list[Flag] = []
    for f in flags:
        if (f.code, f.level) not in seen:
            seen.add((f.code, f.level))
            out.append(f)
    return out


def check_form_fields(labels: list[str], status: str | None = None, page_url: str = "") -> list[Flag]:
    """Visible form labels / placeholders / upload prompts -> block flags. `page_url` is the page showing
    them: account passwords and emailed codes are normal on a known ATS domain."""
    on_ats = registrable_domain(page_url) in KNOWN_ATS_DOMAINS if page_url else False
    ev = _ev(page_url)
    flags: list[Flag] = []
    for label in labels:
        t = " ".join(str(label or "").split())
        if not t:
            continue
        if _REMOTE_FIELD_RE.search(t):
            flags.append(Flag("FIELD_REMOTE_ACCESS", "block", f"asks for remote access: {t}", ev))
        elif _PAYMENT_FIELD_RE.search(t) and not re.search(r"\bfee(s)?[- ]free\b", t, re.I):
            flags.append(Flag("FIELD_PAYMENT", "block", f"asks for a fee or payment details: {t}", ev))
        elif _CREDENTIAL_FIELD_RE.search(t) and (not on_ats or _OTHER_ACCOUNT_RE.search(t)):
            flags.append(Flag("FIELD_CREDENTIALS", "block", f"asks for a password, security answer or code: {t}", ev))
        elif SENSITIVE_FIELD_RE.search(t) and status != "offer":
            flags.append(Flag("FIELD_SENSITIVE_PRE_OFFER", "block",
                              f"asks for identity or bank data before an offer: {t}", ev))
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


