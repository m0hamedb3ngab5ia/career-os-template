"""`careeros doctor` as a subprocess on temp checkouts: before init, right after init (example data = FAIL),
and after the candidate filled everything in (exit 0). PATH is a temp bin dir so tool checks are deterministic."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import EXAMPLE_REPO, PY, personalize, subprocess_env

pytestmark = pytest.mark.integration


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    shutil.copytree(EXAMPLE_REPO, root / "examples")
    return root


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


def fake_bin(tmp_path: Path, tools: tuple[str, ...]) -> Path:
    b = tmp_path / "bin"
    b.mkdir(exist_ok=True)
    for t in tools:
        p = b / t
        p.write_text("#!/bin/sh\nexit 0\n")
        p.chmod(0o755)
    return b


def _cli(root: Path, home: Path, path: Path, *args: str) -> subprocess.CompletedProcess:
    env = subprocess_env(root, home)
    env["PATH"] = str(path)
    env.pop("CLAUDECODE", None)  # a standalone terminal, even when the suite runs inside Claude Code
    return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), *args], capture_output=True, text=True,
                          env=env, timeout=120)


def test_doctor_before_init(checkout: Path, home: Path, tmp_path: Path):
    r = _cli(checkout, home, fake_bin(tmp_path, ("claude",)), "doctor")
    assert r.returncode == 1
    assert "FAIL" in r.stdout and "careeros init" in r.stdout and "Traceback" not in r.stderr


def test_doctor_after_fresh_init_fails_on_example_identity(checkout: Path, home: Path, tmp_path: Path):
    bin_ = fake_bin(tmp_path, ("claude", "tectonic", "gh", "codex"))
    assert _cli(checkout, home, bin_, "init").returncode == 0
    r = _cli(checkout, home, bin_, "doctor")
    assert r.returncode == 1, r.stdout
    assert "FAIL" in r.stdout and "profile/master.yaml: identity.name" in r.stdout and "Alex Example" in r.stdout
    assert "WARN" in r.stdout and "# INSERT" in r.stdout  # untouched placeholders listed
    q = _cli(checkout, home, bin_, "doctor", "--quiet")
    assert q.returncode == 1 and "FAIL" in q.stdout and "WARN" not in q.stdout and "PASS" not in q.stdout
    assert not any(home.iterdir())


def test_doctor_green_after_filling_in(checkout: Path, home: Path, tmp_path: Path):
    bin_ = fake_bin(tmp_path, ("claude", "tectonic", "gh", "codex"))
    assert _cli(checkout, home, bin_, "init").returncode == 0
    personalize(checkout)
    r = _cli(checkout, home, bin_, "doctor")
    assert r.returncode == 0, r.stdout
    assert "FAIL" not in r.stdout.replace("0 fail", "")
    q = _cli(checkout, home, bin_, "doctor", "--quiet")
    assert q.returncode == 0 and q.stdout.strip() == ""


def test_doctor_missing_claude_cli_fails(checkout: Path, home: Path, tmp_path: Path):
    bin_ = fake_bin(tmp_path, ("tectonic",))
    assert _cli(checkout, home, bin_, "init").returncode == 0
    personalize(checkout)
    r = _cli(checkout, home, bin_, "doctor")
    assert r.returncode == 1 and "claude" in r.stdout



def test_doctor_quiet_inside_claude_code_without_cli_on_path(checkout: Path, home: Path, tmp_path: Path):
    bin_ = fake_bin(tmp_path, ("tectonic", "gh", "codex"))
    assert _cli(checkout, home, bin_, "init").returncode == 0
    personalize(checkout)
    env = subprocess_env(checkout, home)
    env.update(PATH=str(bin_), CLAUDECODE="1")
    r = subprocess.run([PY, "-m", "careeros.cli", "--root", str(checkout), "doctor", "--quiet"], capture_output=True,
                       text=True, env=env, timeout=120)
    assert r.returncode == 0 and r.stdout.strip() == ""
