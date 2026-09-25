"""ApplySession: the record of one apply attempt. Pure Python, no browser calls.

    from careeros.apply.session import ApplySession

    s = ApplySession.start(job_id="a1b2c3d4e5f6", ats="greenhouse", apply_url=url)
    s.step("open_tab", ok=True, note=url)
    s.shot(s.screenshot_dir(job_dir) / "01_form.png")
    s.finish("submitted")
    s.save(job_dir)          # -> data/jobs/<id>/apply_session.json, appends to log.md

Outcomes: submitted | needs_review | blocked | failed.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

Outcome = Literal["submitted", "needs_review", "blocked", "failed"]
OUTCOMES: tuple[str, ...] = ("submitted", "needs_review", "blocked", "failed")

SESSION_FILE = "apply_session.json"
LOG_FILE = "log.md"
SCREENSHOT_DIR = "screenshots"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class ApplySession:
    job_id: str
    ats: str
    started: str = field(default_factory=_now)
    finished: str | None = None
    apply_url: str = ""
    tier: str | None = None
    auto_submit: bool = False
    steps: list[dict[str, Any]] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    outcome: str | None = None
    reason: str = ""
    submit_clicked: bool = False
    action_item: dict[str, Any] | None = None
    resume_version: str | None = None
    confirmation_text: str | None = None

    # --- construction ---------------------------------------------------------------

    @classmethod
    def start(cls, job_id: str, ats: str, apply_url: str = "", tier: str | None = None,
              auto_submit: bool = False, resume_version: str | None = None) -> "ApplySession":
        return cls(job_id=job_id, ats=ats, apply_url=apply_url, tier=tier,
                   auto_submit=auto_submit, resume_version=resume_version)

    @classmethod
    def load(cls, job_dir: str | Path) -> "ApplySession | None":
        p = Path(job_dir) / SESSION_FILE
        if not p.exists():
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
        known = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    # --- recording --------------------------------------------------------------------

    def step(self, action: str, ok: bool = True, note: str = "") -> dict[str, Any]:
        entry = {"time": _now(), "action": action, "ok": bool(ok), "note": note}
        self.steps.append(entry)
        return entry

    def shot(self, path: str | Path) -> str:
        p = str(path)
        self.screenshots.append(p)
        return p

    def mark_submit_clicked(self, job_dir: str | Path) -> None:
        """Call right before clicking submit. Persists `submit_clicked` to `job_dir/apply_session.json`
        first, so a crash after the click can never lead to a second one (see `already_submitted`).

        Raises RuntimeError when submit was already clicked (this session or any earlier one for the job)
        or this session may not auto-submit (Tier A).
        """
        if self.submit_clicked or self.already_submitted(job_dir):
            raise RuntimeError(f"refusing to click submit for {self.job_id}: submit already clicked")
        if not self.can_click_submit():
            raise RuntimeError(f"refusing to click submit for {self.job_id}: auto_submit is off for this session")
        self.submit_clicked = True
        self.step("submit_click", ok=True, note="submit clicked once")
        self._write(Path(job_dir))

    @classmethod
    def already_submitted(cls, job_dir: str | Path) -> bool:
        """True when any earlier session for this job dir recorded a submit click (never click again)."""
        prev = cls.load(job_dir)
        return bool(prev and prev.submit_clicked)

    def can_click_submit(self) -> bool:
        return self.auto_submit and not self.submit_clicked

    def finish(self, outcome: str, reason: str = "", action_item: dict[str, Any] | None = None,
               confirmation_text: str | None = None) -> None:
        if outcome not in OUTCOMES:
            raise ValueError(f"outcome must be one of {OUTCOMES}, got {outcome!r}")
        self.outcome = outcome
        self.reason = reason
        self.finished = _now()
        if action_item is not None:
            self.action_item = action_item
        if confirmation_text is not None:
            self.confirmation_text = confirmation_text
        self.step("finish", ok=outcome == "submitted", note=f"{outcome}: {reason}".rstrip(": "))

    # --- paths ------------------------------------------------------------------------

    @staticmethod
    def screenshot_dir(job_dir: str | Path) -> Path:
        d = Path(job_dir) / SCREENSHOT_DIR
        d.mkdir(parents=True, exist_ok=True)
        return d

    def next_screenshot_path(self, job_dir: str | Path, label: str) -> Path:
        n = len(self.screenshots) + 1
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:40]
        return self.screenshot_dir(job_dir) / f"{n:02d}_{safe}.png"

    # --- persistence --------------------------------------------------------------------

    @property
    def status(self) -> str:
        """Tracker status implied by the outcome."""
        return {"submitted": "applied", "needs_review": "needs_review", "blocked": "needs_review",
                "failed": "needs_review"}.get(self.outcome or "", "needs_review")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status
        d["n_steps"] = len(self.steps)
        d["failed_steps"] = [s for s in self.steps if not s["ok"]]
        return d

    def _write(self, jd: Path) -> Path:
        jd.mkdir(parents=True, exist_ok=True)
        p = jd / SESSION_FILE
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)
        return p

    def save(self, job_dir: str | Path) -> Path:
        jd = Path(job_dir)
        p = self._write(jd)
        self._append_log(jd)
        return p

    def _append_log(self, jd: Path) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        outcome = self.outcome or "in_progress"
        shots = f", {len(self.screenshots)} screenshot(s)" if self.screenshots else ""
        line = f"- {ts} [applier] {self.ats} session {outcome}: {self.reason or 'ok'} ({len(self.steps)} steps{shots})"
        if self.action_item:
            line += f"; action item: {self.action_item.get('type', 'other')} - {self.action_item.get('what', '')}"
        with (jd / LOG_FILE).open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def result_line(self) -> str:
        """The `RESULT: {...}` line the apply-job skill prints last."""
        return "RESULT: " + json.dumps({
            "job_id": self.job_id, "ats": self.ats, "outcome": self.outcome, "status": self.status,
            "reason": self.reason, "submit_clicked": self.submit_clicked,
            "screenshots": self.screenshots, "action_item": self.action_item,
            "resume_version": self.resume_version,
        }, ensure_ascii=False)
