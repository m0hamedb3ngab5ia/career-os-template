"""As-submitted snapshots through the CLI: job status/tracker upsert auto-freeze, job freeze, job show."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from conftest import PY, subprocess_env

from careeros.apply.session import ApplySession
from careeros.apply.snapshot import freeze, latest
from careeros.config import Settings
from careeros.models import Posting
from careeros.store import Store

pytestmark = pytest.mark.integration


def _cli(root: Path, home: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), *args], capture_output=True, text=True,
                          input=stdin, env=subprocess_env(root, home), timeout=120)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


def _seed(root: Path, jid: str = "job000000001") -> Path:
    st = Store(Settings.load(root))
    st.save_posting(Posting(job_id=jid, company="Initech", title="Backend Engineer", ats="greenhouse",
                            url="https://x/1"))
    jd = st.job_dir(jid)
    (jd / "resume.pdf").write_bytes(b"%PDF-1.7 test")
    (jd / "cover_letter.txt").write_text("Hi team,")
    (jd / "answers.json").write_text(json.dumps([{"question": "Why Initech?", "answer": "Staplers."}]))
    return jd


def test_job_status_applied_freezes_and_show_lists_it(temp_root: Path, home: Path):
    jd = _seed(temp_root)
    r = _cli(temp_root, home, "job", "status", jd.name, "applied", "--note", "submitted by hand")
    assert r.returncode == 0, r.stderr
    snap = latest(jd)
    assert snap and snap["reason"] == "manual"
    assert {f["name"] for f in snap["files"]} >= {"resume.pdf", "cover_letter.txt", "answers.json", "posting.json"}

    show = _cli(temp_root, home, "job", "show", jd.name)
    assert f"submitted: {snap['frozen_at']} (manual)" in show.stdout
    jobs = json.loads(_cli(temp_root, home, "jobs", "list", "--json").stdout)
    assert jobs[0]["submitted_at"] == snap["frozen_at"]
    assert not any(home.iterdir()), "CLI must not write under HOME"


def test_tracker_upsert_status_applied_freezes(temp_root: Path, home: Path):
    jd = _seed(temp_root)
    r = _cli(temp_root, home, "tracker", "upsert", jd.name, "--field", "Status=applied")
    assert r.returncode == 0, r.stderr
    assert latest(jd)["reason"] == "manual"


def test_job_freeze_with_answers_on_stdin(temp_root: Path, home: Path):
    jd = _seed(temp_root)
    answers = json.dumps([{"label": "Email", "value": "alex@example.com", "source": "standard"}])
    r = _cli(temp_root, home, "job", "freeze", jd.name, "--answers-json", "-", stdin=answers)
    assert r.returncode == 0, r.stderr
    out = Path(r.stdout.strip().split()[-1])
    assert out.parent == jd / "submitted"
    m = json.loads((out / "manifest.json").read_text())
    assert m["answers_entered"][0]["label"] == "Email"
    # explicit freeze always makes a new snapshot; auto-freeze on status does not add one
    assert _cli(temp_root, home, "job", "freeze", jd.name).returncode == 0
    assert _cli(temp_root, home, "job", "status", jd.name, "applied").returncode == 0
    assert len([p for p in (jd / "submitted").iterdir()]) == 2

    assert _cli(temp_root, home, "job", "freeze", "nope").returncode == 1
    bad = _cli(temp_root, home, "job", "freeze", jd.name, "--answers-json", "-", stdin="{not json")
    assert bad.returncode == 2 and "answers-json" in bad.stderr


def test_apply_skill_flow_freezes_once_with_entered_values(temp_root: Path, home: Path):
    """Section 5 of apply-job: finish('submitted') -> freeze(session=s) -> job status applied (no second snapshot)."""
    jd = _seed(temp_root)
    s = ApplySession.start(jd.name, "greenhouse", tier="B", auto_submit=True, resume_version="swe_backend-v1")
    s.record_field("First name", "Alex", "standard")
    s.record_field("Why Initech?", "Staplers.", "essay")
    s.mark_submit_clicked(jd)
    s.finish("submitted", confirmation_text="Application received")
    freeze(jd, session=s)
    s.save(jd)
    assert _cli(temp_root, home, "job", "status", jd.name, "applied").returncode == 0
    snaps = [p for p in (jd / "submitted").iterdir()]
    assert len(snaps) == 1
    m = latest(jd)
    assert m["reason"] == "submitted" and m["resume_version"] == "swe_backend-v1"
    assert [a["value"] for a in m["answers_entered"]] == ["Alex", "Staplers."]


@pytest.mark.parametrize("payload", ["1", "true", '"text"', "null"])
def test_job_freeze_rejects_non_list_answers(temp_root: Path, home: Path, payload: str):
    jd = _seed(temp_root)
    r = _cli(temp_root, home, "job", "freeze", jd.name, "--answers-json", "-", stdin=payload)
    assert r.returncode == 2, r.stderr
    assert "Traceback" not in r.stderr and "answers-json" in r.stderr
    assert not (jd / "submitted").exists()


def test_job_freeze_redacts_password_from_stdin(temp_root: Path, home: Path):
    jd = _seed(temp_root)
    answers = json.dumps([{"label": "Password", "value": "hunter2"}, {"label": "Email", "value": "a@example.com"}])
    r = _cli(temp_root, home, "job", "freeze", jd.name, "--answers-json", "-", stdin=answers)
    assert r.returncode == 0, r.stderr
    out = Path(r.stdout.strip().split()[-1])
    assert "hunter2" not in (out / "manifest.json").read_text()
