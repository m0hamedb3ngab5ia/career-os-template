from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from careeros.config import ConfigError, Settings, get_settings
from careeros.models import Posting
from careeros.scout.ashby import AshbyAdapter
from careeros.scout.base import Adapter, BoardNotFound, FetchError
from careeros.scout.greenhouse import GreenhouseAdapter
from careeros.scout.lever import LeverAdapter
from careeros.store import Store

ADAPTERS: dict[str, type[Adapter]] = {
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "ashby": AshbyAdapter,
}

# Built-in location words per ISO country code, used when that code is in `location.blocked_countries`.
# Extend or override per code with `targets.yaml: location.country_aliases`. Codes not listed anywhere
# fall back to matching the code itself as a word ("Remote (DE)").
COUNTRY_ALIASES: dict[str, list[str]] = {
    "DE": ["germany", "berlin", "munich", "hamburg", "frankfurt"],
    "CN": ["china", "beijing", "shanghai", "shenzhen", "hangzhou"],
    "RU": ["russia", "moscow"],
    "IN": ["india", "bangalore", "bengaluru", "hyderabad", "pune", "mumbai", "chennai", "gurgaon", "noida"],
    "GB": ["united kingdom", "uk", "london", "england"],
    "CA": ["canada", "toronto", "vancouver", "montreal"],
}


@dataclass
class BoardResult:
    company: str
    ats: str
    slug: str
    status: str = "ok"  # ok | bad_slug | error | skipped
    fetched: int = 0
    new: int = 0
    stored: int = 0
    filtered_title: int = 0
    filtered_location: int = 0
    filtered_blocklist: int = 0
    filtered_seniority: int = 0
    error: str = ""
    stored_ids: list[str] = field(default_factory=list)


@dataclass
class ScoutSummary:
    boards: list[BoardResult] = field(default_factory=list)

    @property
    def bad_slugs(self) -> list[BoardResult]:
        return [b for b in self.boards if b.status == "bad_slug"]

    @property
    def errors(self) -> list[BoardResult]:
        return [b for b in self.boards if b.status == "error"]

    @property
    def totals(self) -> dict[str, int]:
        keys = ("fetched", "new", "stored", "filtered_title", "filtered_location", "filtered_blocklist", "filtered_seniority")
        return {k: sum(getattr(b, k) for b in self.boards) for k in keys}


def _kw_regex(keywords: list[str]) -> re.Pattern[str] | None:
    kws = [k for k in keywords if k]
    if not kws:
        return None
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(k) for k in kws) + r")(?![a-z0-9])", re.I)


class Prefilter:
    def __init__(self, settings: Settings):
        self.s = settings
        self.active: dict[str, re.Pattern[str] | None] = {
            cat: _kw_regex(kws) for cat, kws in settings.title_keywords().items()
        }
        self.excluded = _kw_regex(settings.excluded_title_keywords())
        self.senior = _kw_regex(settings.seniority_exclude_keywords())
        self.blocked_countries = settings.blocked_countries()
        self.country_aliases = {**COUNTRY_ALIASES, **settings.country_aliases()}

    def title_category(self, title: str) -> str | None:
        t = title.lower()
        for cat, rx in self.active.items():
            if rx and rx.search(t):
                return cat
        return None

    def title_excluded(self, title: str) -> bool:
        return bool(self.excluded and self.excluded.search(title.lower()))

    def title_senior(self, title: str) -> bool:
        return bool(self.senior and self.senior.search(title.lower()))

    def location_blocked(self, p: Posting) -> bool:
        if not self.blocked_countries:
            return False
        raw_country = str(p.raw.get("country") or "").upper()
        if raw_country and raw_country in self.blocked_countries:
            return True
        addr = p.raw.get("address") or {}
        addr_country = ""
        if isinstance(addr, dict):
            pa = addr.get("postalAddress") or {}
            addr_country = str(pa.get("addressCountry") or "")
            if addr_country.upper() in self.blocked_countries:
                return True
        # Ashby's addressCountry is usually a full name ("Germany"), so run it through the aliases too.
        loc = f"{p.location or ''} {addr_country}".lower()
        for code in self.blocked_countries:
            for alias in self.country_aliases.get(code, [code.lower()]):
                if re.search(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])", loc):
                    return True
        return False

    def check(self, p: Posting) -> tuple[bool, str, str | None]:
        """Return (passes, reason, category)."""
        if self.s.is_blocklisted(p.company):
            return False, "blocklist", None
        cat = self.title_category(p.title)
        if cat is None or self.title_excluded(p.title):
            return False, "title", cat
        if self.title_senior(p.title):
            return False, "seniority", cat
        if self.location_blocked(p):
            return False, "location", cat
        return True, "ok", cat


def run_scout(
    settings: Settings | None = None,
    store: Store | None = None,
    only: list[str] | None = None,
    log=print,
) -> ScoutSummary:
    s = settings or get_settings()
    st = store or Store(s)
    pf = Prefilter(s)
    if not any(pf.active.values()):
        # Every title would fail the prefilter and be marked seen for good; refuse instead.
        raise ConfigError("no active category has title_keywords in config/categories.yaml; refusing to scout")
    seen = st.load_seen()
    summary = ScoutSummary()

    for board in s.boards:
        company = str(board.get("company", "?"))
        ats = str(board.get("ats", "")).lower()
        slug = str(board.get("slug") or board.get("url") or "")
        if only and not any(o.lower() in (company.lower(), slug.lower()) for o in only):
            continue
        res = BoardResult(company=company, ats=ats, slug=slug)
        summary.boards.append(res)

        if ats == "custom":
            res.status = "skipped"
            res.error = "custom scraper not implemented"
            log(f"[scout] {company}: custom scraper not implemented ({slug})")
            continue
        cls = ADAPTERS.get(ats)
        if cls is None:
            res.status = "error"
            res.error = f"unknown ats '{ats}'"
            log(f"[scout] {company}: {res.error}")
            continue

        try:
            postings = cls().fetch(board)
        except BoardNotFound:
            res.status = "bad_slug"
            res.error = "404 bad slug"
            log(f"[scout] {company} ({ats}/{slug}): 404 bad slug")
            continue
        except FetchError as e:
            res.status = "error"
            res.error = str(e)[:200]
            log(f"[scout] {company} ({ats}/{slug}): error {res.error}")
            continue
        except Exception as e:  # noqa: BLE001
            res.status = "error"
            res.error = f"{type(e).__name__}: {e}"[:200]
            log(f"[scout] {company} ({ats}/{slug}): error {res.error}")
            continue

        res.fetched = len(postings)
        new_ids: list[str] = []
        for p in postings:
            if p.job_id in seen:
                continue
            new_ids.append(p.job_id)
            ok, reason, cat = pf.check(p)
            if not ok:
                setattr(res, f"filtered_{reason}", getattr(res, f"filtered_{reason}") + 1)
                continue
            p.raw["prefilter_category"] = cat
            st.save_posting(p)
            st.append_log(p.job_id, f"found via {ats}/{slug}; prefilter category={cat}", component="scout")
            res.stored += 1
            res.stored_ids.append(p.job_id)
        res.new = len(new_ids)
        seen.update(new_ids)
        st.save_seen(seen)
        log(
            f"[scout] {company:<22} {ats:<10} fetched={res.fetched:<4} new={res.new:<4} stored={res.stored:<3} "
            f"(title-{res.filtered_title} loc-{res.filtered_location} block-{res.filtered_blocklist} senior-{res.filtered_seniority})"
        )

    return summary


__all__ = ["run_scout", "Prefilter", "ScoutSummary", "BoardResult", "ADAPTERS"]
