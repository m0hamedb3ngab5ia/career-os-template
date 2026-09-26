"""Every Settings page: which YAML key each control writes, its range, its default and whether that default is the
"(Recommended)" one. Defaults come from the loaders' own constants where they exist and otherwise equal
examples/config (tests/test_settings_schema.py keeps both in step). Config keys win over the mockup's sample names.

Why Python and not a YAML schema file: defaults and ranges reference the loaders' constants (DEFAULT_PRESETS,
retention.DEFAULTS, ...) so they can't drift, per-value checks reuse the loaders' own validators, and a typo in a
field is an import-time error instead of a runtime one.
"""
from __future__ import annotations

from typing import Any

from careeros import retention
from careeros.config import ATS_WITH_SLUG, ConfigError
from careeros.runs import advisor, policy, schedule
from careeros.runs import config as runs_cfg
from careeros.safety import ghost
from careeros.ui.settings_schema.model import Field, Group, Policy, Section

P, T, C, Q = "pipeline", "targets", "companies", "qa"

# Every safety check code (src/careeros/safety/scam.py, ghost.py); a test keeps this in step with the source.
SAFETY_CODES = (
    "SCAM_PAYMENT_REQUEST", "SCAM_REMOTE_ACCESS_REQUEST", "SCAM_BRAND_DOMAIN_MISMATCH", "SCAM_APPLY_DOMAIN_UNRECOGNIZED",
    "SCAM_FREE_EMAIL_RECRUITER", "SCAM_CHAT_ONLY_INTERVIEW", "SCAM_NO_INTERVIEW", "SCAM_SALARY_IMPLAUSIBLE",
    "SCAM_FLAGGED_BEFORE", "FIELD_PAYMENT", "FIELD_CREDENTIALS", "FIELD_REMOTE_ACCESS", "FIELD_SENSITIVE_PRE_OFFER",
    "COMPANY_NOT_YET_CHECKED", "COMPANY_SPARSE_PUBLIC_FOOTPRINT", "COMPANY_CONTRADICTIONS",
    "GHOST_OLD_POST", "GHOST_STALE_NO_ACTIVITY", "GHOST_REPOSTED", "GHOST_HIRING_FREEZE", "GHOST_RECENT_LAYOFFS",
    "GHOST_AGGREGATOR_ONLY",
)
ATS_FAMILIES = ("greenhouse", "lever", "ashby", "workday", "icims", "taleo", "smartrecruiters", "jobvite",
                "successfactors", "custom")
PAUSE_TRIGGERS = ("captcha", "account_creation_email_verify", "question_not_in_standard_answers",
                  "salary_field_freeform", "bot_detection_suspected", "file_upload_failed", "qa_failed_twice")
REVIEW_ARTIFACTS = ("resume", "cover_letter", "answers", "form")
_AUTO_TOKEN = policy._TOKEN_RE.pattern.strip("^$")


# --- per-value checks that reuse the loaders ----------------------------------------------------------------

def _schedule_check(kind: str):
    def check(v: Any) -> str | None:
        try:
            schedule._job(kind, v, runs_cfg.PRESET_NAMES)
        except ConfigError as e:
            return str(e).split(": ", 1)[-1].replace("config/pipeline.yaml: schedule", "schedule")
        return None
    return check


def _tier_rules(v: list[dict[str, Any]]) -> str | None:
    for i, r in enumerate(v, 1):
        if set(r) != {"if", "tier"}:
            return f"Rule {i} needs a condition and a tier."
        if not isinstance(r["if"], str) or not r["if"].strip():
            return f"Rule {i}: the condition is empty."
        if r["tier"] not in ("A", "B", "C"):
            return f"Rule {i}: tier must be A, B or C."
    return None


def _season(v: dict[Any, Any]) -> str | None:
    try:
        policy._volume({"volume": {"season_multiplier": v}})
    except ConfigError as e:
        return str(e).split("volume.", 1)[-1]
    return None


def _domains(v: dict[Any, Any]) -> str | None:
    for company, d in v.items():
        ok = isinstance(d, str) and d.strip() or (isinstance(d, list) and d and
                                                  all(isinstance(x, str) and x.strip() for x in d))
        if not ok:
            return f"{company}: enter a domain like example.com, or a list of them."
    return None


def _boards(v: list[dict[str, Any]]) -> str | None:
    for i, b in enumerate(v, 1):
        if not b.get("company") or not b.get("ats"):
            return f"Board {i} needs a company and an ATS."
        ats = str(b["ats"]).lower()
        if ats in ATS_WITH_SLUG and not str(b.get("slug") or "").strip():
            return f"Board {i} ({b['company']}) needs a {ats} slug."
        if ats not in ATS_WITH_SLUG and not str(b.get("url") or "").strip():
            return f"Board {i} ({b['company']}) needs a careers page URL."
    return None


# --- cross-field checks (field ids -> effective values) -----------------------------------------------------

def _greater(lo_id: str, hi_id: str, lo_label: str, unit: str = "days"):
    def check(values: dict[str, Any]) -> list[tuple[str, str]]:
        lo, hi = values.get(lo_id), values.get(hi_id)
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and hi <= lo:
            return [(hi_id, f"Must be more than {lo_label} ({lo:g} {unit}). Enter {lo + 1:g} or more.")]
        return []
    return check


def _min_below_max(values: dict[str, Any]) -> list[tuple[str, str]]:
    lo, hi = values.get("qa:cover_letter.min_words"), values.get("qa:cover_letter.max_words")
    if isinstance(lo, int) and isinstance(hi, int) and lo >= hi:
        return [("qa:cover_letter.min_words", f"Must be less than the maximum ({hi} words).")]
    return []


# --- fields -------------------------------------------------------------------------------------------------

def _num(file: str, key: str, label: str, default: Any, *, lo: float | None = 0, hi: float | None = None,
         integer: bool = True, unit: str = "", help: str = "", recommended: bool = True, control: str = "number",
         step: float | None = None, nullable: bool = False, personal: bool = False) -> Field:
    return Field(file, key, control, label, help=help, default=None if personal else default,
                 recommended=recommended and not personal, personal=personal, min=lo, max=hi, integer=integer,
                 unit=unit, step=step, nullable=nullable)


def _switch(file: str, key: str, label: str, default: bool, help: str = "", **kw: Any) -> Field:
    return Field(file, key, "switch", label, help=help, default=default, **kw)


def _tags(file: str, key: str, label: str, default: Any, help: str = "", options: tuple = (), strict: bool = False,
          personal: bool = False, **kw: Any) -> Field:
    return Field(file, key, "tags", label, help=help, default=None if personal else default,
                 recommended=not personal, personal=personal, options=options, strict_options=strict, **kw)


def _personal(file: str, key: str, control: str, label: str, help: str = "", **kw: Any) -> Field:
    return Field(file, key, control, label, help=help, default=None, recommended=False, personal=True, **kw)


R = runs_cfg.DEFAULT_RANKING
TO = runs_cfg.DEFAULT_TIMEOUTS
G = ghost.DEFAULTS
RET = retention.DEFAULTS
ST, AD = advisor.STORAGE_DEFAULTS, advisor.ADVISOR_DEFAULTS
JOBS = schedule.DEFAULT_JOBS
AS = policy.DEFAULT_AUTO_SUBMIT

NEVER_APPLY = Policy("Applying", "Runs never apply in this version",
                     "Scheduled and manual runs score and prepare only; you submit every application.")
TIER_A = Policy("Tier A auto-submit", "Never", "Dream companies are always submitted by you.")
LINKEDIN = Policy("LinkedIn messages", "Draft only", "LinkedIn is never automated; you send every message.")
THANK_YOU = Policy("Thank-you notes after interviews", "Always written by you",
                   "Thank-you notes are never drafted or sent automatically.")
OUTREACH_FIELDS = (
    _switch(P, "outreach.manual_if_connected", "Tailor by hand when you're already connected", True,
            "1st-degree LinkedIn connections never get an automated message; they become an Action Item."),
    _switch(P, "outreach.manual_if_mutuals", "Tailor by hand when you have mutual connections", True,
            "Anyone with mutuals is handled by hand. Record what LinkedIn shows with `careeros outreach mark`."),
)


def _tier(t: str, desc: str, auto: bool, cover: str, outreach: str, review: list[str]) -> Group:
    locked = t == "A"
    return Group(f"tier_{t.lower()}", f"Tier {t}", (
        Field(T, f"tiers.{t}.description", "text", "Description", default=desc),
        Field(T, f"tiers.{t}.auto_submit", "switch", "Auto-submit when you run Apply", default=auto,
              locked=locked, note="Tier A is never auto-submitted, whatever the file says." if locked else "",
              help="Only after QA passes, on an allowed ATS, with a pass safety verdict."),
        Field(T, f"tiers.{t}.cover_letter", "select", "Cover letter", default=cover,
              options=("always", "if_required")),
        Field(T, f"tiers.{t}.outreach", "select", "Outreach", default=outreach,
              options=("always", "if_contact_found", "never")),
        Field(T, f"tiers.{t}.review_required", "tags", "You review", default=review, options=REVIEW_ARTIFACTS,
              help="Documents you check before anything is submitted. Empty = only QA failures reach you."),
    ))


SECTIONS: tuple[Section, ...] = (
    Section("general", "General", (
        Group("files", "Files", (
            Field(P, "paths.tracker_xlsx", "text", "Tracker spreadsheet", default="data/JobTracker.xlsx",
                  help="Where JobTracker.xlsx is exported. Relative to the repo, or ~/… for anywhere."),
        )),
        Group("claude", "Claude", (
            Policy("Runs use", "Your Claude Code subscription", "No API key; `claude -p` runs each skill."),
            Field(P, "llm.model_hint", "text", "Model", default=None, nullable=True,
                  help="Empty = Claude Code's default (Recommended). For example: sonnet."),
        )),
        Group("resume", "Résumé", (
            Field(P, "resume_build.engine", "select", "LaTeX engine", default="tectonic",
                  options=("tectonic", "pdflatex")),
            Policy("Résumé length", "One page", "A hard QA rule."),
        )),
    )),
    Section("targets", "Targets", (
        Group("candidate", "You", (
            _personal(T, "candidate.level", "select", "Level", options=("new_grad", "early_career")),
            _personal(T, "candidate.graduation", "text", "Graduation", pattern=r"\d{4}-(0[1-9]|1[0-2])",
                      help="Year and month, e.g. 2026-05."),
            _num(T, "candidate.current_base_usd", "Current base salary", None, unit="USD", nullable=True,
                 personal=True),
            _num(T, "candidate.min_base_usd", "Minimum base salary", None, unit="USD", personal=True,
                 help="Postings whose top of range is below this are skipped. Unknown salary is allowed."),
            _num(T, "candidate.salary_dropdown_floor_usd", "Salary dropdown floor", None, unit="USD", personal=True,
                 help="When a form offers ranges, the lowest bucket at or above this is picked."),
            _personal(T, "candidate.work_authorization", "select", "Work authorization",
                      options=("us_citizen", "permanent_resident", "visa")),
            _personal(T, "candidate.needs_sponsorship", "switch", "Needs sponsorship"),
        )),
        Group("location", "Location", (
            _tags(T, "location.preferred", "Preferred cities", None, personal=True, help='As "City ST".'),
            _tags(T, "location.preferred_regions", "Preferred countries", None, personal=True,
                  help="ISO country codes, e.g. US."),
            _tags(T, "location.allowed_countries", "Allowed countries", None, personal=True,
                  help='"*" allows anywhere not blocked.'),
            _tags(T, "location.blocked_countries", "Blocked countries", None, personal=True),
            _personal(T, "location.remote_ok", "switch", "Remote roles are fine"),
        )),
        Group("roles", "Roles", (
            _tags(T, "seniority.exclude_title_keywords", "Skip titles containing",
                  ["senior", "sr.", "staff", "principal", "lead", "manager", "director", "head of", "vp",
                   "vice president", "distinguished", "architect", "fellow", "intern", "internship", "co-op", "phd",
                   "postdoc", "chief"]),
            _tags(T, "categories.primary", "Primary categories",
                  ["swe_backend", "swe_fullstack", "data_engineering", "swe_platform"],
                  help="Category ids from categories.yaml."),
            _tags(T, "categories.secondary", "Secondary categories",
                  ["ml_engineering", "swe_mobile", "quant_dev", "sre_devops"]),
            _tags(T, "categories.excluded", "Excluded categories",
                  ["product_manager", "sales_eng", "support", "qa_manual", "hardware"]),
            _tags(T, "industries.boost", "Industries to rank higher", None, personal=True),
            _tags(T, "industries.blocked", "Industries to never apply to", None, personal=True),
        )),
        Group("thresholds", "Fit thresholds", (
            _num(T, "thresholds.min_fit_to_prepare", "Minimum fit to prepare", 70, hi=100),
            _num(T, "thresholds.min_fit_nonpreferred_location", "Minimum fit outside preferred cities", 85, hi=100),
            _num(T, "thresholds.boost_industry_bonus", "Boost for preferred industries", 5, hi=100, unit="points"),
            _num(T, "thresholds.tier_a_min_fit", "Minimum fit for dream companies", 60, hi=100),
        )),
    )),
    Section("autonomy", "Autonomy", (
        _tier("A", "dream firms — full prep, the candidate submits", False, "always", "always",
              ["resume", "cover_letter", "answers", "form"]),
        _tier("B", "strong fit — auto-submit after QA", True, "always", "if_contact_found", []),
        _tier("C", "volume", True, "if_required", "never", []),
        Group("tier_rules", "Tier rules", (
            Field(T, "tier_rules", "rule_list", "Rules", check=_tier_rules,
                  default=[{"if": "company_in dream_list", "tier": "A"}, {"if": "fit >= 85", "tier": "B"},
                           {"if": "fit >= 70", "tier": "C"}],
                  help="First match wins."),
        )),
        Group("volume", "Volume", (
            _num(T, "volume.max_applications_per_day", "Applications per day", 15, lo=1),
            _num(T, "volume.max_per_company_per_90_days", "Applications per company in 90 days", 2, lo=1),
            _num(T, "volume.same_company_cooldown_days", "Cooldown after a rejection", 30, unit="days"),
            _num(T, "volume.deadline_cluster_days", "Apply together when deadlines are within", 7, unit="days"),
            Field(T, "volume.season_multiplier", "key_value", "Busy-month multiplier", check=_season,
                  default={"9": 2.0, "10": 1.5, "1": 2.0, "2": 1.5},
                  help="Month (1–12) → multiplier on applications per day."),
        )),
        Group("outreach", "Outreach", (LINKEDIN, *OUTREACH_FIELDS, THANK_YOU)),
    )),
    Section("safety", "Safety", (
        Group("ats", "Where auto-submit is allowed", (
            _tags(T, "safety.auto_submit_ats", "Auto-submit on", ["greenhouse", "lever", "ashby"],
                  options=ATS_FAMILIES, strict=True),
            _tags(T, "safety.assisted_ats", "Prepare only (you submit) on",
                  ["workday", "icims", "taleo", "smartrecruiters", "jobvite", "successfactors", "custom"],
                  options=ATS_FAMILIES, strict=True),
            _tags(T, "safety.pause_on", "Always stop and ask on", list(PAUSE_TRIGGERS), options=PAUSE_TRIGGERS),
        )),
        Group("scam", "Scam checks", (
            _num(T, "safety.scam.salary_max_multiple", "Review salaries above", 3, lo=1, integer=False,
                 unit="× your minimum", step=0.5),
        )),
        Group("ghost", "Ghost jobs", (
            _num(T, "safety.ghost.old_post_days", "Old post", G["old_post_days"], lo=1, unit="days",
                 help="Older lowers confidence only."),
            _num(T, "safety.ghost.very_old_post_days", "Very old post", G["very_old_post_days"], lo=1, unit="days",
                 help="Older goes to review."),
            _num(T, "safety.ghost.recent_update_days", "Recently updated within", G["recent_update_days"], lo=1,
                 unit="days"),
            _num(T, "safety.ghost.repost_window_days", "Repost window", G["repost_window_days"], lo=1, unit="days"),
            _num(T, "safety.ghost.repost_flag_count", "Review after this many reposts", G["repost_flag_count"],
                 lo=2),
            _num(T, "safety.ghost.freeze_window_days", "Hiring freeze counts for", G["freeze_window_days"], lo=1,
                 unit="days"),
            _num(T, "safety.ghost.layoff_window_days", "Layoffs count for", G["layoff_window_days"], lo=1,
                 unit="days"),
        )),
        Group("levels", "Check levels", (
            Field(T, "safety.levels", "reason_levels", "Change a check's level", default={}, options=SAFETY_CODES,
                  help="Block, skip, review, info or off per check. Empty = each check's built-in level."),
        )),
    ), checks=(_greater("targets:safety.ghost.old_post_days", "targets:safety.ghost.very_old_post_days",
                        "Old post"),)),
    Section("scout", "Scout", (
        Group("sources", "Sources", (
            _tags(T, "scout.sources", "Job boards to fetch", ["greenhouse", "lever", "ashby"],
                  options=("greenhouse", "lever", "ashby"), strict=True),
            _tags(C, "searches.keywords", "Search phrases", None, personal=True),
        )),
        Group("filters", "Filters", (
            _switch(T, "scout.filters.blocklist", "Skip blocked companies", True),
            _switch(T, "scout.filters.flagged", "Skip companies flagged as scams", True),
            _switch(T, "scout.filters.title", "Keep only matching titles", True),
            _switch(T, "scout.filters.seniority", "Skip senior titles", True),
            _switch(T, "scout.filters.location", "Skip blocked countries", True),
            _switch(T, "scout.filters.ghost", "Skip likely ghost jobs", True),
        )),
    )),
    Section("companies", "Companies", (
        Group("dream", "Dream companies", (
            _tags(C, "dream_list", "Dream companies", None, personal=True,
                  help="Tier A: full prep, you submit, outreach first."),
        )),
        Group("blocklist", "Never apply", (
            _tags(C, "blocklist.companies", "Companies", None, personal=True,
                  help="Include your current employer."),
            _tags(C, "blocklist.industries", "Industries", None, personal=True),
            _tags(C, "blocklist.name_patterns", "Name contains", None, personal=True,
                  help="Lowercase parts of company names."),
        )),
        Group("domains", "Company domains", (
            Field(C, "company_domains", "key_value", "Official domains", default={}, check=_domains,
                  help="Company → its real domain(s), for the brand look-alike check."),
        )),
        Group("boards", "Job boards", (
            _personal(C, "boards", "records", "Boards", check=_boards,
                      help="One row per company: ATS and slug, or a careers page URL for custom."),
        )),
    )),
    Section("outreach", "Outreach", (
        Group("people", "People you know", (LINKEDIN, *OUTREACH_FIELDS, THANK_YOU)),
    )),
    Section("notifications", "Notifications", (
        Group("notify", "Notify me", (
            Field(P, "notify.on_interview", "select", "Interview invite", default="push", options=("push", "none")),
            Field(P, "notify.on_offer", "select", "Offer", default="push", options=("push", "none")),
            Field(P, "notify.on_qa_fail", "select", "QA failure", default="action_item_only",
                  options=("action_item_only", "push", "none")),
            _switch(P, "notify.daily_digest", "Daily digest", True),
        )),
    )),
    Section("runs", "Runs & schedule", (
        Group("budget", "Budget", (
            Field(P, "runs.preset", "preset_cards", "Budget", default=runs_cfg.RECOMMENDED_PRESET,
                  options=runs_cfg.PRESET_NAMES, help="A run stops at whichever limit comes first."),
            Field(P, "runs.presets", "key_value", "Preset sizes", default=runs_cfg.DEFAULT_PRESETS, readonly=True,
                  note="Fixed sizes; choose custom for your own numbers."),
            _num(P, "runs.custom.max_score_jobs", "Custom: jobs to score", 25, lo=1),
            _num(P, "runs.custom.max_prepare_jobs", "Custom: jobs to prepare", 5, lo=1),
            _num(P, "runs.custom.max_minutes", "Custom: time limit", 90, lo=1, unit="min"),
        )),
        Group("timeouts", "Timeouts and failures", (
            _num(P, "runs.job_timeout_minutes.score", "Score timeout per job", TO["score"], lo=1, unit="min"),
            _num(P, "runs.job_timeout_minutes.prepare", "Prepare timeout per job", TO["prepare"], lo=1, unit="min"),
            _num(P, "runs.job_timeout_minutes.inbox_sync", "Inbox sync timeout", TO["inbox_sync"], lo=1, unit="min"),
            _switch(P, "runs.stop_on_timeout", "Stop the run on a timeout", True,
                    "A hung call usually means a login or prompt wait."),
            _num(P, "runs.max_consecutive_failures", "Stop after failures in a row", 3, lo=1),
        )),
        Group("ranking", "Ranking", (
            _num(P, "runs.ranking.freshness_weight", "Freshness", R["freshness_weight"], hi=100, control="slider",
                 unit="points"),
            _num(P, "runs.ranking.fresh_hours", "Fresh for", R["fresh_hours"], lo=1, unit="hours"),
            _num(P, "runs.ranking.stale_days", "Stale at", R["stale_days"], lo=1, unit="days"),
            _num(P, "runs.ranking.dream_bonus", "Dream company bonus", R["dream_bonus"], hi=100, control="slider",
                 unit="points"),
            _num(P, "runs.ranking.deadline_bonus", "Deadline bonus", R["deadline_bonus"], hi=100, control="slider",
                 unit="points"),
            _num(P, "runs.ranking.deadline_days", "Deadline within", R["deadline_days"], lo=1, unit="days"),
            _num(P, "runs.ranking.fit_weight", "Fit weight (prepare)", R["fit_weight"], hi=5, integer=False,
                 control="slider", step=0.1, unit="points per fit point"),
            _num(P, "runs.ranking.retry_bonus", "Retry bonus", R["retry_bonus"], hi=100, control="slider",
                 unit="points"),
        ), help="Which jobs go first. No Claude involved."),
        Group("retry", "Retry", (
            _num(P, "runs.retry.max_attempts", "Attempts per job", policy.DEFAULT_RETRY["max_attempts"], lo=1,
                 help="2 = retry once."),
            _switch(P, "runs.retry.action_item", "Then add an Action Item", policy.DEFAULT_RETRY["action_item"]),
        )),
        Group("prepare", "Prepare", (
            _switch(P, "runs.prepare.stop_at_daily_cap", "Stop preparing at today's apply cap", True),
        )),
        Group("auto_submit", "Auto-submit", (
            NEVER_APPLY,
            TIER_A,
            Field(P, "runs.auto_submit.enabled", "switch", "Scheduled runs may submit", default=AS["enabled"],
                  readonly=True, note="Runs never apply in this version."),
            Field(P, "runs.auto_submit.allow", "rule_list", "Allowed", default=AS["allow"], pattern=_AUTO_TOKEN,
                  help="tier_a | tier_b | tier_c, fit_gte_<n>, fit_lt_<n>, dream, category_<name>."),
            Field(P, "runs.auto_submit.manual", "rule_list", "Always manual", default=AS["manual"],
                  pattern=_AUTO_TOKEN, help="Wins over Allowed. fit_gte_85 keeps your best matches manual."),
        )),
        Group("checks", "Before each run", (
            _switch(P, "runs.preflight_doctor", "Run `careeros doctor` first", True),
            _tags(P, "runs.required_mcp_servers", "Required MCP servers", [],
                  help="Servers every run needs logged in. Inbox sync carries its own gmail."),
            _num(P, "runs.job_lock_minutes", "Job lock expires after", 120, lo=1, unit="min"),
        )),
        Group("tools", "Allowed tools", (
            _tags(P, "llm.allowed_tools", "Tools a run may use", runs_cfg.DEFAULT_ALLOWED_TOOLS,
                  help='A tool missing here ends a run with "Tool not allowed", never a hang.'),
        )),
        Group("schedule", "Schedule", (
            Field(P, "schedule.jobs.scout", "schedule", "Scout", default=JOBS["scout"],
                  check=_schedule_check("scout"), help="Every 2–3 hours. Ignores quiet hours."),
            Field(P, "schedule.jobs.inbox_sync", "schedule", "Inbox sync", default=JOBS["inbox_sync"],
                  check=_schedule_check("inbox_sync"), help="Off until the inbox-sync skill is finished."),
            Field(P, "schedule.jobs.score", "schedule", "Score", default=JOBS["score"],
                  check=_schedule_check("score")),
            Field(P, "schedule.jobs.prepare", "schedule", "Prepare", default=JOBS["prepare"],
                  check=_schedule_check("prepare"), help="Never applies."),
            Field(P, "schedule.jobs.prune", "schedule", "Prune", default=JOBS["prune"],
                  check=_schedule_check("prune")),
            _num(P, "schedule.tick_minutes", "Check every", 15, lo=1, unit="min"),
            _num(P, "schedule.missed_after_minutes", "Missed after", 60, lo=1, unit="min",
                 help="Slots missed while the Mac was off collapse into one catch-up you start."),
        )),
        Group("quiet", "Quiet hours", (
            Field(P, "schedule.quiet_hours", "time_range", "Quiet hours",
                  default={"start": schedule.DEFAULT_QUIET[0], "end": schedule.DEFAULT_QUIET[1]}, nullable=True,
                  help="Score, prepare and inbox sync never start inside it. Scout and prune ignore it."),
            Field(P, "schedule.timezone", "text", "Time zone", default="local",
                  help="local, or an IANA name like America/New_York."),
        )),
    )),
    Section("storage", "Storage & efficiency", (
        Group("limits", "Storage limits", (
            _num(P, "storage.budget_mb", "Storage budget", ST["budget_mb"], lo=1, unit="MB"),
            _num(P, "storage.warn_at_pct", "Warn at", ST["warn_at_pct"], lo=1, hi=100, unit="% of budget"),
            _num(P, "storage.disk_free_warn_pct", "Warn when disk free is under", ST["disk_free_warn_pct"], hi=100,
                 unit="%"),
        )),
        Group("retention", "Retention", (
            _num(P, "retention.screenshots_after_closed_days", "Screenshots of closed jobs",
                 RET["screenshots_after_closed_days"], unit="days", help="0 turns a rule off."),
            _switch(P, "retention.keep_confirmation_screenshot", "Keep the confirmation screenshot",
                    RET["keep_confirmation_screenshot"]),
            _num(P, "retention.unprepared_posting_days", "Unprepared postings", RET["unprepared_posting_days"],
                 unit="days"),
            _num(P, "retention.run_logs_days", "Run logs", RET["run_logs_days"], unit="days"),
            _num(P, "retention.run_summaries_days", "Run summaries", RET["run_summaries_days"], unit="days"),
        )),
        Group("advisor", "Advisor", (
            _num(P, "advisor.advise_after_days", "Storage advice after", AD["advise_after_days"], lo=1, unit="days"),
            _num(P, "advisor.prune_idle_weeks", "Suggest keeping more after", AD["prune_idle_weeks"], lo=1,
                 unit="weeks of nothing pruned"),
            _num(P, "advisor.min_runs", "Run advice after", AD["min_runs"], lo=1, unit="runs of a kind"),
            _num(P, "advisor.window_days", "Looking back", AD["window_days"], lo=1, unit="days"),
            _num(P, "advisor.usage_limit_stops", "Smaller preset after", AD["usage_limit_stops"], lo=1,
                 unit="usage-limit stops"),
            _num(P, "advisor.failure_rate_warn", "Warn when failures exceed", AD["failure_rate_warn"], hi=1,
                 integer=False, step=0.05, unit="share of jobs"),
        )),
    )),
    Section("qa", "Quality checks", (
        Group("critic", "Critic", (
            _num(Q, "critic.pass_threshold", "Pass mark", 7.5, lo=1, hi=10, integer=False, step=0.1,
                 unit="out of 10"),
            _num(Q, "critic.max_regenerations", "Regenerate before asking you", 1, unit="times"),
        )),
        Group("cover_letter", "Cover letter", (
            _num(Q, "cover_letter.min_words", "Minimum length", 120, lo=1, unit="words"),
            _num(Q, "cover_letter.max_words", "Maximum length", 250, lo=1, unit="words"),
            _num(Q, "cover_letter.hard.company_facts_min", "Company facts at least", 2),
            _num(Q, "cover_letter.soft.voice_match_min", "Voice match at least", 7, lo=1, hi=10),
            _num(Q, "cover_letter.soft.specificity_min", "Specificity at least", 7, lo=1, hi=10),
        )),
        Group("resume", "Résumé", (
            _num(Q, "resume.soft.keyword_coverage_min", "Keyword coverage at least", 0.6, hi=1, integer=False,
                 step=0.05, unit="share of required skills"),
            _num(Q, "resume.soft.bullet_max_words", "Flag bullets longer than", 35, lo=1, unit="words"),
            _tags(Q, "resume.soft.weak_openers", "Weak openers",
                  ["worked on", "helped", "responsible for", "assisted", "participated in", "involved in",
                   "tasked with"]),
        )),
        Group("answers", "Application answers", (
            _num(Q, "answers.soft.voice_match_min", "Voice match at least", 7, lo=1, hi=10),
        )),
        Group("banned", "Banned phrases", (
            _tags(Q, "banned_phrases", "Never write", [
                "spearheaded", "leveraged", "leverage", "passionate about", "fast-paced environment",
                "I am excited to apply", "I am writing to express", "proven track record", "results-driven",
                "synergy", "dynamic", "thrilled", "delve", "tapestry", "testament to", "in today's",
                "game-changer", "cutting-edge", "hit the ground running", "wear many hats",
                "I believe I would be a great fit", "Dear Hiring Manager,"]),
        )),
    ), checks=(_min_below_max,)),
)

# Example config keys with no form control, and why. The coverage test fails on any key that is in neither.
NOT_IN_UI: dict[tuple[str, str], str] = {
    (P, "paths.jobs_dir"): "Data location; changing it moves where every job is read and written.",
    (P, "paths.seen_file"): "Data location; changing it moves where every job is read and written.",
    (P, "paths.profile"): "Profile files are edited outside the UI (free text, not settings).",
    (P, "paths.standard_answers"): "Profile files are edited outside the UI (free text, not settings).",
    (P, "paths.voice_dir"): "Profile files are edited outside the UI (free text, not settings).",
    (P, "paths.resume_template_dir"): "Templates are edited outside the UI (LaTeX, not settings).",
    (P, "paths.output_dir_per_job"): "Layout switch the code assumes is on; not a preference.",
    (P, "schedule.launchd_label"): "LaunchAgent id; change it only after `careeros schedule uninstall`.",
    (P, "llm.runner"): "Shown as a locked row: runs use the Claude Code subscription; the API is not enabled.",
    (P, "llm.headless_cmd"): "The exact claude command line; a wrong flag breaks every run.",
    (P, "resume_build.fallback"): "Only one fallback exists (markdown_to_pdf); nothing to choose.",
    (Q, "resume.max_pages"): "Shown as a locked row: a one-page résumé is a hard rule.",
    (Q, "resume.hard"): "Hard truth and ATS rules the QA gate always enforces; not switches.",
    (Q, "cover_letter.hard.truth_trace"): "Hard truth rule the QA gate always enforces; not a switch.",
    (Q, "cover_letter.hard.names_role_and_company"): "Hard rule the QA gate always enforces; not a switch.",
    (Q, "cover_letter.hard.no_banned_phrases"): "Hard rule the QA gate always enforces; not a switch.",
    (Q, "answers.hard"): "Hard truth rules the QA gate always enforces; not switches.",
    (Q, "resume.soft.date_format"): "Must match the LaTeX template's date format; edit both together.",
    (Q, "resume.soft.scale_words"): "Tuning list for the metric heuristic; edit qa.yaml if you need to.",
    (Q, "critic.model_rubric"): "The critic's rubric names are read by the qa-review skill; not a preference.",
    (Q, "style_rules"): "Mixed rule list read by the writing skills; edit qa.yaml if you need to.",
    (C, "already_applied"): "Past-application records; the tracker holds applications made here.",
    (C, "hiring_signals"): "Written by `careeros safety signal`; a record, not a setting.",
    (C, "searches.sources"): "Discovery sources carry URLs and notes; edit companies.yaml.",
    (C, "prestige_tiers"): "Company ranking tables; edit companies.yaml.",
    (C, "prestige_scoring"): "Company ranking bonuses; edit companies.yaml.",
    ("categories", "*"): "Category definitions (keywords, bullet_priority ids from master.yaml) are edited in "
                         "categories.yaml; Targets picks which categories are primary, secondary or excluded.",
}
