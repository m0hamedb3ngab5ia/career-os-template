"""`careeros job add` / `job describe` as a real subprocess on a temp repo (REQ-153)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from conftest import PY, make_temp_root, subprocess_env

pytestmark = pytest.mark.integration


def _run(root: Path, home: Path, *args: str, stdin: str | None = None):
    return subprocess.run([PY, "-m", "careeros.cli", *args], env=subprocess_env(root, home), cwd=root,
                          input=stdin, capture_output=True, text=True, timeout=60)


def test_add_from_alert_describe_and_dedup(tmp_path):
    root, home = make_temp_root(tmp_path / "repo"), tmp_path / "home"
    home.mkdir()
    alert = json.dumps([{"title": "SWE", "company": "Acme", "url": "https://www.linkedin.com/jobs/view/42?trk=x"}])
    r = _run(root, home, "job", "add", "--from-alert", "-", stdin=alert)
    assert r.returncode == 0 and r.stdout.startswith("added"), r.stderr
    jid = r.stdout.split()[1]
    d = root / "data" / "jobs" / jid
    assert json.loads((d / "posting.json").read_text())["raw"]["needs_description"] is True
    assert json.loads((d / "status.json").read_text())["status"] == "found"
    assert _run(root, home, "job", "add", "--from-alert", "-", stdin=alert).stdout.startswith("exists")
    r = _run(root, home, "job", "describe", jid, "--text-file", "-", stdin="Python backend role.")
    assert r.returncode == 0, r.stderr
    post = json.loads((d / "posting.json").read_text())
    assert post["description_text"] == "Python backend role." and not post["raw"].get("needs_description")
    r = _run(root, home, "job", "add", "https://app.joinhandshake.com/jobs/9")
    assert r.returncode == 1 and "signed-in browser" in r.stderr
