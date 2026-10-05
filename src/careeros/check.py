"""Check a job (REQ-114, REQ-116, UC-010, FLOW-003).

Pasted/uploaded JD -> `source: manual` posting via Store.save_posting (REQ-109 scan + flags.json), then the usual
`run score --job` (posting text wrapped as untrusted, TASK-001) and the résumé match table (match.matches). No résumé
>= threshold -> one "Tailor from master" offer = one `run prepare --job` (match.pick: tweak or tailor). A tailored
attempt still below the threshold -> notice + ask: keep (flagged `below_threshold`, saved as a tailored résumé) or
discard. State lives in the job's check.json.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from careeros import match, resumes
from careeros.extract import extract_text
from careeros.models import Posting
from careeros.runs.status import run_state
from careeros.runs.store import RunStore
from careeros.store import Store

MAX_BYTES = resumes.MAX_BYTES  # REQ-114: <= 5 MB, same cap as résumé uploads
TEXT_TYPES = (".txt", ".md")
CHECK = "check.json"
_ATTEMPT_GLOBS = ("resume.*", "resume_choice.json", "cover_letter.*", "qa.json", "prepare.json", "answers.json")


class BadInput(ValueError):
    """No text / bad field -> 422."""


class Refused(Exception):
    """The check is not at the step this action needs (one tailor run per check, decide only when asked) -> 409."""


def text_from(filename: str | None, data: bytes) -> str:
    """JD text from a paste (no filename) or a pdf/docx/txt/md file. Only the extension of `filename` is used."""
    if len(data) > MAX_BYTES:
        raise resumes.TooLarge(f"{filename or 'pasted text'}: larger than {MAX_BYTES // (1024 * 1024)} MB")
    ext = Path(filename).suffix.lower() if filename else ""
    if not filename or ext in TEXT_TYPES:
        text = data.decode("utf-8", errors="replace")
    elif ext in resumes.MAGIC and data.startswith(resumes.MAGIC[ext]):
        with tempfile.TemporaryDirectory() as d:  # our own path; the client's filename never touches disk
            p = Path(d) / f"jd{ext}"
            p.write_bytes(data)
            text = extract_text(p)
    else:
        raise resumes.BadType(f"{filename}: only PDF, DOCX, TXT or MD job descriptions are accepted")
    text = text.strip()
    if not text:
        raise BadInput(f"{filename or 'pasted text'}: no text found")
    return text


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _job_dir(settings: Any, job_id: str) -> Path:
    d = Store(settings).job_dir(job_id)
    if not re.fullmatch(r"[\w-]+", job_id or "") or not (d / "posting.json").exists():
        raise LookupError(f"job {job_id} not found")
    return d


def _load(jd: Path) -> dict[str, Any]:
    return match._json(jd / CHECK)


def _save(jd: Path, c: dict[str, Any]) -> None:
    (jd / CHECK).write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def create(settings: Any, text: str, *, title: str = "", company: str = "", url: str = "") -> dict[str, Any]:
    """Store the JD as a manual posting (scanned on save). The same text again is the same job."""
    if url and not url.lower().startswith(("http://", "https://")):
        raise BadInput("url must start with http:// or https://")
    title = title.strip() or next((ln.strip() for ln in text.splitlines() if ln.strip()), "")[:120]
    p = Posting(company=company.strip() or "Unknown company", title=title, url=url, ats="manual",
                ats_job_id=hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], source_slug="manual",
                description_text=text)
    store = Store(settings)
    store.save_posting(p)
    jd = store.job_dir(p.job_id)
    if not (jd / CHECK).exists():
        _save(jd, {"source": "manual", "created_at": _now(), "tailor": None, "decision": None})
    flags = store.load_flags(p.job_id)
    return {"job_id": p.job_id, "flagged": bool(flags.get("injection_suspected")),
            "reasons": flags.get("injection_reasons") or []}


def _attempt(settings: Any, jd: Path) -> dict[str, Any] | None:
    """The tailor run's résumé scored like every other résumé, once prepare wrote it."""
    if match._json(jd / "resume_choice.json").get("action") not in ("tweak", "tailor") \
            or not (jd / "resume.txt").exists():
        return None
    sc, posting = match._json(jd / "score.json"), match._json(jd / "posting.json")
    m = match.score((jd / "resume.txt").read_text(encoding="utf-8"), sc.get("required_skills") or [],
                    sc.get("preferred_skills") or sc.get("nice_to_have_skills") or [],
                    str(posting.get("title") or ""), (settings.pipeline.get("match") or {}).get("synonyms") or {})
    return {"score": m["score"], "missing": m["missing"]}


def _run_done(settings: Any, c: dict[str, Any]) -> bool:
    """The tailor run ended (prepare may regenerate resume.txt until then)."""
    rs = RunStore(settings)
    run = rs.load_run((c.get("tailor") or {}).get("run_id") or "")
    return bool(run) and run_state(rs, run) != "running"


def holds_save(settings: Any, jd: Path) -> bool:
    """A check's tailored attempt below the threshold is not saved by the runner; keep saves it, discard never."""
    if not (jd / CHECK).exists() or not (a := _attempt(settings, jd)):
        return False
    return a["score"] < match.matches(settings, jd)["threshold"]


def state(settings: Any, job_id: str) -> dict[str, Any]:
    """stage: scoring | ready | not_tailorable | offer_tailor | tailoring | tailor_failed | ready_tailored | confirm |
    below_threshold | discarded."""
    jd = _job_dir(settings, job_id)
    c, m = _load(jd), match.matches(settings, jd)
    thr, rows = m["threshold"], m["resumes"]
    best = rows[0]["score"] if rows else None
    out: dict[str, Any] = {**m, "tailor_run": (c.get("tailor") or {}).get("run_id"), "decision": c.get("decision"),
                           "attempt": None, "notice": None}
    if not m["scored"]:
        stage = "scoring"
    elif best is not None and best >= thr:
        stage = "ready"
    elif c.get("decision") == "discard":
        stage = "discarded"
    elif not c.get("tailor") and (sc := match._json(jd / "score.json")).get("decision") != "prepare":
        stage = "not_tailorable"  # prepare would refuse it (runner eligibility): no dead-end offer
        out["notice"] = (f"score decision {sc.get('decision')}"
                         + (f": {sc['skip_reason']}" if sc.get("skip_reason") else "") + "; no tailoring for this job")
    elif not c.get("tailor"):
        stage = "offer_tailor"
    elif not _run_done(settings, c):
        stage = "tailoring"
    elif not (a := _attempt(settings, jd)):
        stage = "tailor_failed"  # run ended without a résumé: one more try allowed
    else:
        out["attempt"] = a
        if a["score"] >= thr:
            stage = "ready_tailored"
        elif c.get("decision") == "keep":
            stage = "below_threshold"
        else:
            stage = "confirm"
        if stage != "ready_tailored":
            x = a["score"]  # the attempt's score and its missing list (REQ-116)
            out["notice"] = (f"threshold not met: best {x}, needed {thr} ({x}/{thr}); missing: "
                             + (", ".join(a["missing"]) or "none") + ". Create closest match anyway?")
    out["stage"] = stage
    return out


def tailor(settings: Any, job_id: str, start: Callable[[], str]) -> str:
    """The one "Prepare application" run of this check (REQ-114): above threshold = plain prepare, below = tailor
    from master (REQ-116). `start` starts `run prepare --job` (ticks the job) and returns its run id."""
    st, jd = state(settings, job_id), _job_dir(settings, job_id)
    if not (st["stage"] in ("offer_tailor", "tailor_failed") or (st["stage"] == "ready" and not _load(jd).get("tailor"))):
        raise Refused(f"job {job_id}: no prepare offer at stage {st['stage']!r} (max one prepare run per check)")
    run_id = start()
    _save(jd, {**_load(jd), "tailor": {"run_id": run_id, "started_at": _now()}})
    return run_id


def decide(settings: Any, job_id: str, keep: bool) -> dict[str, Any]:
    """Answer "Create closest match anyway?": keep the attempt flagged `below_threshold`, or discard it."""
    st = state(settings, job_id)
    if st["stage"] != "confirm":
        raise Refused(f"job {job_id}: nothing to keep or discard at stage {st['stage']!r}")
    jd = _job_dir(settings, job_id)
    if keep:
        choice = match._json(jd / "resume_choice.json")
        (jd / "resume_choice.json").write_text(json.dumps({**choice, "below_threshold": True}, indent=2,
                                                          ensure_ascii=False) + "\n", encoding="utf-8")
        Store(settings).set_flag(job_id, "below_threshold", True)
        if match._json(jd / "qa.json").get("pass"):  # QA-failed text never becomes a reusable résumé
            match.save_tailored(settings, jd, below_threshold=True)
    else:
        from careeros.tracker import set_status_both

        for pat in _ATTEMPT_GLOBS:
            for f in jd.glob(pat):
                f.unlink(missing_ok=True)
        set_status_both(settings, job_id, "scored", "check: tailored attempt discarded")
    _save(jd, {**_load(jd), "decision": "keep" if keep else "discard", "below_threshold": keep,
               "decided_at": _now()})
    return state(settings, job_id)
