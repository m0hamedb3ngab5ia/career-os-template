from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from careeros.apply import snapshot
from careeros.apply.session import ApplySession
from careeros.models import Posting
from careeros.store import Store

pytestmark = pytest.mark.unit


def _job(tmp_path: Path, jid: str = "abc123def456") -> Path:
    jd = tmp_path / "jobs" / jid
    jd.mkdir(parents=True)
    (jd / "posting.json").write_text(json.dumps({"job_id": jid, "company": "Acme", "title": "SWE"}))
    (jd / "resume.pdf").write_bytes(b"%PDF-1.7 v1")
    (jd / "resume.txt").write_text("resume v1")
    (jd / "resume.json").write_text(json.dumps({"meta": {"resume_version": "swe_backend-v2"}}))
    (jd / "cover_letter.md").write_text("Hi team,\n")
    (jd / "answers.json").write_text(json.dumps([{"question": "Why us?", "answer": "Because."}]))
    return jd


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_freeze_copies_existing_documents_and_writes_manifest(tmp_path):
    jd = _job(tmp_path)
    out = snapshot.freeze(jd)
    assert out.parent == jd / "submitted"
    names = sorted(p.name for p in out.iterdir())
    assert names == ["answers.json", "cover_letter.md", "manifest.json", "posting.json",
                     "resume.json", "resume.pdf", "resume.txt"]
    m = json.loads((out / "manifest.json").read_text())
    assert m["job_id"] == "abc123def456"
    assert m["reason"] == "manual"
    assert m["resume_version"] == "swe_backend-v2"
    assert m["frozen_at"].endswith("+00:00")
    files = {f["name"]: f for f in m["files"]}
    assert set(files) == set(names) - {"manifest.json"}
    assert files["resume.pdf"]["sha256"] == _sha(jd / "resume.pdf")
    assert files["resume.pdf"]["bytes"] == len(b"%PDF-1.7 v1")
    assert m["answers_entered"] == []


def test_snapshot_survives_regeneration(tmp_path):
    jd = _job(tmp_path)
    out = snapshot.freeze(jd)
    os.chmod(jd / "resume.txt", 0o644)
    (jd / "resume.txt").write_text("resume v2, regenerated")
    assert (out / "resume.txt").read_text() == "resume v1"


def test_snapshot_files_are_read_only(tmp_path):
    out = snapshot.freeze(_job(tmp_path))
    for p in out.iterdir():
        assert not (p.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)), p.name


def test_freeze_never_overwrites(tmp_path, monkeypatch):
    jd = _job(tmp_path)
    monkeypatch.setattr(snapshot, "_stamp", lambda: "20260926T120000Z")
    a = snapshot.freeze(jd)
    b = snapshot.freeze(jd, reason="manual")
    assert a != b and a.exists() and b.exists()
    assert b.name == "20260926T120000Z-2"


def test_finder_duplicates_are_ignored(tmp_path):
    jd = _job(tmp_path)
    (jd / "resume 2.pdf").write_bytes(b"dup")
    out = snapshot.freeze(jd)
    assert not (out / "resume 2.pdf").exists()
    (jd / "submitted" / f"{out.name} 2").mkdir()
    assert snapshot.latest(jd)["dir"] == str(out)


def test_answers_entered_list_and_mapping_forms(tmp_path):
    jd = _job(tmp_path)
    out = snapshot.freeze(jd, answers_entered=[{"label": "Email", "value": "a@example.com", "source": "standard"}])
    m = json.loads((out / "manifest.json").read_text())
    assert m["answers_entered"] == [{"label": "Email", "value": "a@example.com", "source": "standard"}]
    out2 = snapshot.freeze(jd, answers_entered={"Phone": "555-0100"})
    m2 = json.loads((out2 / "manifest.json").read_text())
    assert m2["answers_entered"] == [{"label": "Phone", "value": "555-0100", "source": None}]


def test_bad_reason_rejected(tmp_path):
    with pytest.raises(ValueError):
        snapshot.freeze(_job(tmp_path), reason="because")


def test_reason_and_answers_come_from_the_apply_session(tmp_path):
    jd = _job(tmp_path)
    s = ApplySession.start("abc123def456", "greenhouse", auto_submit=True, resume_version="swe_backend-v2")
    s.record_field("First name", "Alex", "standard")
    s.record_field("Why us?", "Because.", "essay")
    s.mark_submit_clicked(jd)
    s.finish("submitted", confirmation_text="Thanks for applying")
    m = json.loads((snapshot.freeze(jd, session=s) / "manifest.json").read_text())
    assert m["reason"] == "submitted"
    assert m["confirmation_text"] == "Thanks for applying"
    assert [a["label"] for a in m["answers_entered"]] == ["First name", "Why us?"]
    assert "apply_session.json" in {f["name"] for f in m["files"]}


def test_saved_assisted_session_gives_assisted_stop(tmp_path):
    jd = _job(tmp_path)
    s = ApplySession.start("abc123def456", "greenhouse", tier="A", auto_submit=False)
    s.record_field("Email", "alex@example.com", "standard")
    s.finish("needs_review", reason="assisted: review & submit")
    s.save(jd)
    m = json.loads((snapshot.freeze(jd) / "manifest.json").read_text())
    assert m["reason"] == "assisted_stop"
    assert m["answers_entered"][0]["value"] == "alex@example.com"


def test_latest_none_then_newest(tmp_path, monkeypatch):
    jd = _job(tmp_path)
    assert snapshot.latest(jd) is None
    stamps = iter(["20260101T000000Z", "20260201T000000Z"])
    monkeypatch.setattr(snapshot, "_stamp", lambda: next(stamps))
    snapshot.freeze(jd)
    newest = snapshot.freeze(jd)
    assert snapshot.latest(jd)["dir"] == str(newest)


def test_record_field_roundtrips_through_session_file(tmp_path):
    jd = _job(tmp_path)
    s = ApplySession.start("abc123def456", "lever")
    s.record_field("LinkedIn", "https://linkedin.com/in/x", "standard")
    s.save(jd)
    assert ApplySession.load(jd).entered == [{"label": "LinkedIn", "value": "https://linkedin.com/in/x",
                                               "source": "standard"}]


def _store_job(settings, jid="j1") -> Store:
    st = Store(settings)
    st.save_posting(Posting(job_id=jid, company="Acme", title="SWE", ats="greenhouse"))
    (st.job_dir(jid) / "resume.pdf").write_bytes(b"%PDF")
    return st


def test_status_applied_freezes_once(settings):
    st = _store_job(settings)
    st.set_status("j1", "queued")
    assert snapshot.latest(st.job_dir("j1")) is None
    st.set_status("j1", "applied")
    first = snapshot.latest(st.job_dir("j1"))
    assert first and first["reason"] == "manual"
    st.set_status("j1", "applied", "again")
    assert len(list((st.job_dir("j1") / "submitted").iterdir())) == 1
    assert "frozen" in st.read_log("j1")


def test_list_jobs_reports_submitted_at(settings):
    st = _store_job(settings)
    assert st.list_jobs()[0]["submitted_at"] is None
    st.set_status("j1", "applied")
    assert st.list_jobs()[0]["submitted_at"] == snapshot.latest(st.job_dir("j1"))["frozen_at"]


# --- secrets never recorded (review #20) -------------------------------------------------------------

@pytest.mark.parametrize("label", [
    "Password", "Confirm password", "Create Password*", "Passcode", "Verification code", "Enter the 6-digit code",
    "One-time code", "OTP", "Security code", "Security question", "Answer to security question", "API key",
    "Access token", "Client secret", "Code",
])
def test_record_field_redacts_secrets(label):
    s = ApplySession.start("abc123def456", "workday")
    e = s.record_field(label, "hunter2", "profile")
    assert e["value"] == "<redacted>"
    assert s.entered[-1]["value"] == "<redacted>"


@pytest.mark.parametrize("label", [
    "Zip code", "Postal Code", "Country code", "Phone country code", "Area code", "Promo code", "Referral code",
    "First name", "Email", "Why us?",
])
def test_record_field_keeps_ordinary_fields(label):
    s = ApplySession.start("abc123def456", "workday")
    assert s.record_field(label, "07030", "profile")["value"] == "07030"


def test_session_file_never_holds_a_secret_appended_directly(tmp_path):
    jd = _job(tmp_path)
    s = ApplySession.start("abc123def456", "workday")
    s.entered.append({"label": "Password", "value": "hunter2", "source": "profile"})
    s.save(jd)
    assert "hunter2" not in (jd / "apply_session.json").read_text()


def test_freeze_redacts_answers_passed_in(tmp_path):
    jd = _job(tmp_path)
    out = snapshot.freeze(jd, answers_entered=[{"label": "Password", "value": "hunter2"},
                                               {"label": "Zip code", "value": "07030"}])
    text = (out / "manifest.json").read_text()
    assert "hunter2" not in text
    m = json.loads(text)
    assert [a["value"] for a in m["answers_entered"]] == ["<redacted>", "07030"]
    out2 = snapshot.freeze(jd, answers_entered={"Verification code": "123456"})
    assert json.loads((out2 / "manifest.json").read_text())["answers_entered"][0]["value"] == "<redacted>"


def test_freeze_redacts_secrets_in_saved_session(tmp_path):
    jd = _job(tmp_path)
    (jd / "apply_session.json").write_text(json.dumps({
        "job_id": "abc123def456", "ats": "workday",
        "entered": [{"label": "Password", "value": "hunter2", "source": "profile"}]}))
    out = snapshot.freeze(jd)
    assert json.loads((out / "manifest.json").read_text())["answers_entered"][0]["value"] == "<redacted>"


# --- auto-freeze never blocks a status change (review #20) -------------------------------------------

@pytest.mark.parametrize("target,exc", [
    ("freeze", PermissionError("denied")),
    ("latest", PermissionError("denied")),
    ("latest", json.JSONDecodeError("bad", "{", 0)),
    ("freeze", ValueError("each entered answer needs a 'label'")),
])
def test_status_applied_survives_snapshot_failure(settings, monkeypatch, target, exc):
    st = _store_job(settings)

    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(snapshot, target, boom)
    st.set_status("j1", "applied")
    assert st.get_status("j1") == "applied"
    assert "snapshot failed" in st.read_log("j1")


def test_manifest_written_atomically(tmp_path, monkeypatch):
    jd = _job(tmp_path)
    real = Path.write_text
    calls = []

    def spy(self, *a, **k):
        calls.append(self.name)
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "write_text", spy)
    out = snapshot.freeze(jd)
    assert "manifest.json" not in calls and any(c.startswith("manifest.json") for c in calls)
    assert sorted(p.name for p in out.iterdir() if p.name.startswith("manifest")) == ["manifest.json"]
    assert json.loads((out / "manifest.json").read_text())["job_id"] == "abc123def456"
