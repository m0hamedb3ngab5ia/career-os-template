"""`careeros notify digest --dry-run --html FILE` as a real subprocess on a temp repo (REQ-155)."""
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


def test_digest_dry_run_writes_html_with_apply_list(tmp_path):
    root, home = make_temp_root(tmp_path / "repo"), tmp_path / "home"
    home.mkdir()
    alert = json.dumps([{"title": "Backend Engineer", "company": "Acme", "url": "https://www.linkedin.com/jobs/view/42"}])
    r = _run(root, home, "job", "add", "--from-alert", "-", stdin=alert)
    assert r.returncode == 0, r.stderr
    jid = r.stdout.split()[1]
    assert _run(root, home, "job", "status", jid, "queued").returncode == 0
    out = tmp_path / "digest.html"
    r = _run(root, home, "notify", "digest", "--dry-run", "--html", str(out))
    assert r.returncode == 0, r.stderr
    assert "Apply to these" in r.stdout and "Backend Engineer" in r.stdout
    page = out.read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>") and "Backend Engineer" in page and "<script" not in page
