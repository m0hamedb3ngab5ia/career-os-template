from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

STATUSES: tuple[str, ...] = (
    "found",
    "scored",
    "skipped",
    "queued",
    "prepared",
    "needs_review",
    "applied",
    "screening",
    "interview",
    "offer",
    "rejected",
    "withdrawn",
    "ghosted",
)
Status = Literal[
    "found", "scored", "skipped", "queued", "prepared", "needs_review", "applied",
    "screening", "interview", "offer", "rejected", "withdrawn", "ghosted",
]

ACTION_TYPES: tuple[str, ...] = (
    "captcha", "review", "question", "salary", "bot_detection", "qa_fail",
    "send_linkedin", "send_email", "profile_gap", "laptop_required", "scam_suspected", "other",
)
ActionType = Literal[
    "captcha", "review", "question", "salary", "bot_detection", "qa_fail",
    "send_linkedin", "send_email", "profile_gap", "laptop_required", "scam_suspected", "other",
]

# What the user needs on hand to complete an action item (tracker `Needs` column).
ACTION_NEEDS: tuple[str, ...] = ("laptop", "phone", "anytime")
ActionNeeds = Literal["laptop", "phone", "anytime"]

Tier = Literal["A", "B", "C"]
Priority = Literal["H", "M", "L"]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_job_id(ats: str, company: str, ats_job_id: str | None, url: str | None) -> str:
    key = f"{ats}:{company}:{ats_job_id or url or ''}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


class Posting(BaseModel):
    job_id: str = ""
    company: str
    title: str
    location: str = ""
    remote: bool | None = None
    url: str = ""
    apply_url: str = ""
    ats: str
    ats_job_id: str | None = None
    posted_at: str | None = None
    description_text: str = ""
    description_html: str = ""
    departments: list[str] = Field(default_factory=list)
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    source_slug: str = ""
    fetched_at: str = Field(default_factory=now_iso)
    raw: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _fill_job_id(self) -> "Posting":
        if not self.job_id:
            self.job_id = make_job_id(self.ats, self.company, self.ats_job_id, self.url)
        return self


class Score(BaseModel):
    job_id: str
    category: str
    fit: int = Field(ge=0, le=100)
    tier: Tier | None = None
    prestige: str | None = None
    hard_filter_fails: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    salary_ok: bool | None = None
    location_ok: bool | None = None
    scored_at: str = Field(default_factory=now_iso)

    @property
    def passes(self) -> bool:
        return not self.hard_filter_fails


class QACheck(BaseModel):
    name: str
    kind: Literal["hard", "soft"] = "hard"
    passed: bool
    detail: str = ""
    score: float | None = None


class QAResult(BaseModel):
    job_id: str
    artifact: Literal["resume", "cover_letter", "answers", "form"]
    passed: bool
    checks: list[QACheck] = Field(default_factory=list)
    critic_scores: dict[str, float] = Field(default_factory=dict)
    critic_mean: float | None = None
    regenerations: int = 0
    notes: str = ""
    reviewed_at: str = Field(default_factory=now_iso)

    @property
    def hard_fails(self) -> list[QACheck]:
        return [c for c in self.checks if c.kind == "hard" and not c.passed]


class ActionItem(BaseModel):
    id: str = ""
    created: str = Field(default_factory=now_iso)
    job_id: str = ""
    company: str = ""
    role: str = ""
    type: ActionType = "other"
    what: str
    link: str = ""
    priority: Priority = "M"
    needs: ActionNeeds = "anytime"
    done: bool = False
    done_date: str | None = None


class Contact(BaseModel):
    job_id: str = ""
    company: str
    name: str
    title: str = ""
    linkedin: str = ""
    email: str = ""
    email_confidence: str = ""
    draft_message: str = ""
    sent: bool = False
    sent_date: str | None = None
    replied: str = ""


class TrackerRow(BaseModel):
    job_id: str
    company: str | None = None
    role: str | None = None
    category: str | None = None
    tier: str | None = None
    prestige: str | None = None
    fit: int | None = None
    location: str | None = None
    remote: str | None = None
    salary: str | None = None
    url: str | None = None
    date_found: str | None = None
    date_applied: str | None = None
    status: Status | None = None
    ats: str | None = None
    resume_version: str | None = None
    cover_letter: str | None = None
    qa_score: float | None = None
    override: str | None = None
    last_email_date: str | None = None
    next_action: str | None = None
    next_action_date: str | None = None
    notes: str | None = None
    folder: str | None = None

    @classmethod
    def from_posting(cls, p: Posting, score: Score | None = None, folder: str | None = None) -> "TrackerRow":
        salary = None
        if p.salary_min or p.salary_max:
            lo = f"{int(p.salary_min):,}" if p.salary_min else "?"
            hi = f"{int(p.salary_max):,}" if p.salary_max else "?"
            salary = f"{lo}-{hi}" + (f" {p.salary_currency}" if p.salary_currency else "")
        remote = None if p.remote is None else ("Y" if p.remote else "N")
        row = cls(
            job_id=p.job_id,
            company=p.company,
            role=p.title,
            location=p.location or None,
            remote=remote,
            salary=salary,
            url=p.url or p.apply_url or None,
            date_found=p.fetched_at[:10],
            ats=p.ats,
            folder=folder,
        )
        if score:
            row.category = score.category
            row.tier = score.tier
            row.prestige = score.prestige
            row.fit = score.fit
        return row
