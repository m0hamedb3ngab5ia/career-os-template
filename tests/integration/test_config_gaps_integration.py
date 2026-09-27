"""The Settings rows that gained a config key, end to end: saved through the Settings service (comments kept) on a
temp root, then the real CLI honours them. A fake `claude` is first on PATH; no network."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from conftest import EXAMPLE_REPO, FIXTURES, PY, personalize, subprocess_env

from careeros.config import Settings
from careeros.models import Posting
from careeros.store import Store
from careeros.ui.services import settings_io
from careeros.ui.services.settings_io import SettingsInvalid

pytestmark = pytest.mark.integration


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.fixture
def fake_bin(tmp_path: Path) -> Path:
    b = tmp_path / "bin"
    b.mkdir()
    exe = b / "claude"
    exe.write_text(f"#!{PY}\n" + (FIXTURES / "fake_claude.py").read_text())
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return b


@pytest.fixture
def root(temp_root: Path) -> Path:
    r = personalize(temp_root)  # runs refuse to start on the example candidate
    shutil.copy(EXAMPLE_REPO / "config" / "pipeline.yaml", r / "config" / "pipeline.yaml")  # commented example
    return r


@pytest.fixture
def env(root: Path, home: Path, fake_bin: Path) -> dict[str, str]:
    e = subprocess_env(root, home)
    e["PATH"] = f"{fake_bin}{os.pathsep}{e['PATH']}"
    e.pop("CLAUDECODE", None)
    return e


def cli(root: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), *args], capture_output=True, text=True,
                          env=env, timeout=120, cwd=root)


def save(root: Path, section: str, changes: dict) -> None:
    settings_io.save_section(Settings.load(root), section, changes)


def add_posting(root: Path, **kw) -> str:
    p = Posting(**{"company": "Acme", "title": "Backend Software Engineer", "ats": "greenhouse", "ats_job_id": "r1",
                   "url": "https://boards.greenhouse.io/acme/jobs/1",
                   "apply_url": "https://boards.greenhouse.io/acme/jobs/1", "description_text": "python apis " * 40,
                   "posted_at": (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat(), **kw})
    Store(Settings.load(root)).save_posting(p)
    return p.job_id


def test_new_rows_read_as_their_recommended_defaults(root):
    s = Settings.load(root)
    vals = {sec: settings_io.read_section(s, sec)["values"] for sec in ("outreach", "safety", "runs")}
    assert vals["outreach"]["pipeline:outreach.mutuals_threshold"] == 1
    assert vals["safety"]["targets:safety.pause_auto_submit"] is False
    assert vals["runs"]["pipeline:schedule.missed_runs"] == "ask"
    assert vals["runs"]["pipeline:schedule.scout_quiet_hours"] is False
    assert vals["runs"]["pipeline:runs.on_usage_limit"] == "stop"


def test_bad_values_are_refused_and_nothing_is_written(root):
    p, t = root / "config" / "pipeline.yaml", root / "config" / "targets.yaml"
    pb, tb = p.read_text(), t.read_text()
    with pytest.raises(SettingsInvalid) as e:
        save(root, "outreach", {"pipeline:outreach.mutuals_threshold": 0})
    assert "pipeline:outreach.mutuals_threshold" in e.value.fields
    with pytest.raises(SettingsInvalid) as e:
        save(root, "runs", {"pipeline:runs.on_usage_limit": "retry", "pipeline:schedule.missed_runs": "run"})
    assert set(e.value.fields) == {"pipeline:runs.on_usage_limit", "pipeline:schedule.missed_runs"}
    with pytest.raises(SettingsInvalid):
        save(root, "safety", {"targets:safety.pause_auto_submit": "yes"})
    assert p.read_text() == pb and t.read_text() == tb


def test_a_hand_edited_bad_value_fails_the_cli_closed(root, env):
    p = root / "config" / "pipeline.yaml"
    p.write_text(p.read_text().replace("mutuals_threshold: 1 ", "mutuals_threshold: many "))
    jid = add_posting(root)
    (root / "data" / "jobs" / jid / "contacts.json").write_text(json.dumps({"contacts": []}))
    r = cli(root, env, "outreach", "check", jid)
    assert r.returncode != 0 and "outreach.mutuals_threshold" in r.stderr


def test_mutuals_threshold_decides_who_is_tailored_by_hand(root, env):
    jid = add_posting(root)
    (root / "data" / "jobs" / jid / "contacts.json").write_text(json.dumps({"job_id": jid, "contacts": [
        {"name": "Jane Doe", "role": "recruiter", "linkedin_degree": 2, "mutuals": 2},
        {"name": "Sam Lee", "role": "team_lead", "linkedin_degree": 2, "mutuals": 4}]}))
    before = json.loads(cli(root, env, "outreach", "check", jid).stdout)
    assert [c["manual"] for c in before["contacts"]] == [True, True]      # default 1: any mutual

    save(root, "outreach", {"pipeline:outreach.mutuals_threshold": 3})
    assert "mutuals_threshold: 3 " in (root / "config" / "pipeline.yaml").read_text()  # comment kept
    after = json.loads(cli(root, env, "outreach", "check", jid).stdout)
    assert [c["manual"] for c in after["contacts"]] == [False, True]
    assert after["action_text"] == "tailor manually: Sam Lee (4 mutual connections)"


def test_pause_auto_submit_turns_the_apply_gate_off(root, env):
    jid = add_posting(root, description_text="Build APIs. Questions: jobs@acme.com")
    assert cli(root, env, "safety", "check", jid).returncode == 0
    safety = root / "data" / "jobs" / jid / "safety.json"
    assert json.loads(safety.read_text())["auto_submit_allowed"] is True

    save(root, "safety", {"targets:safety.pause_auto_submit": True})
    r = cli(root, env, "safety", "check", jid)
    assert r.returncode == 0, r.stderr                                    # the verdict is still pass
    out = json.loads(safety.read_text())
    assert out["verdict"] == "pass" and out["auto_submit_allowed"] is False
    assert "safety.pause_auto_submit" in out["auto_submit_reason"]


def test_usage_limit_pause_pauses_runs_until_resume(root, env):
    jid = add_posting(root)
    (root / "data" / "jobs" / jid / ".fake_mode").write_text("usage_limit")
    save(root, "runs", {"pipeline:runs.on_usage_limit": "pause"})
    r = cli(root, env, "run", "score")
    assert r.returncode == 1 and "usage_limit" in r.stdout
    st = json.loads(cli(root, env, "run", "status", "--json").stdout)
    assert st["paused"] and "usage limit" in st["paused"]["reason"] and st["paused"]["until"] is None
    again = json.loads(cli(root, env, "run", "score", "--json").stdout)
    assert again["stop_reason"] == "paused"
    assert cli(root, env, "run", "resume").returncode == 0
    assert json.loads(cli(root, env, "run", "status", "--json").stdout)["paused"] is None


def test_usage_limit_stop_default_leaves_runs_unpaused(root, env):
    jid = add_posting(root)
    (root / "data" / "jobs" / jid / ".fake_mode").write_text("usage_limit")
    assert cli(root, env, "run", "score").returncode == 1
    assert json.loads(cli(root, env, "run", "status", "--json").stdout)["paused"] is None


def _schedule_for_tick(root: Path) -> None:
    p = root / "config" / "pipeline.yaml"
    data = yaml.safe_load(p.read_text())
    data["schedule"]["jobs"]["scout"]["enabled"] = False       # scout does HTTP; no network in tests
    data["schedule"]["quiet_hours"] = None
    data["schedule"]["jobs"]["score"] = {"every_hours": 6}
    data["schedule"]["jobs"]["prepare"] = {"every_hours": 12}
    p.write_text(yaml.safe_dump(data, sort_keys=False))


def _pretend_asleep(root: Path) -> None:
    state = root / "data" / "runs" / "schedule.json"
    s = json.loads(state.read_text())
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    s["last_tick"] = old
    for k in s["jobs"]:
        s["jobs"][k]["last_run"] = old
    state.write_text(json.dumps(s))


@pytest.mark.parametrize("choice,pending", [("ask", True), ("skip", False)])
def test_missed_runs_choice_decides_the_catch_up_prompt(root, env, choice, pending):
    add_posting(root)
    _schedule_for_tick(root)
    save(root, "runs", {"pipeline:schedule.missed_runs": choice})
    assert cli(root, env, "tick", "--json").returncode == 0
    _pretend_asleep(root)
    out = json.loads(cli(root, env, "tick", "--json").stdout)
    assert "missed" in {d["action"] for d in out["decisions"]} and not out["results"]
    st = json.loads(cli(root, env, "run", "status", "--json").stdout)
    assert bool(st["catch_up"]) is pending
