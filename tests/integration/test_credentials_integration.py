"""`careeros creds ...` and the doctor credentials check via subprocess on a temp root with a temp HOME."""
from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import PY, make_temp_root, subprocess_env

pytestmark = pytest.mark.integration
SECRET = "Tr0ub4dor-and-3"


def _cli(root: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), *args], capture_output=True, text=True,
                          input=stdin, env=subprocess_env(root, root.parent / "home"), timeout=120)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = make_temp_root(tmp_path / "repo")
    (tmp_path / "home").mkdir()
    return r


def test_creds_cli_roundtrip_never_prints_the_secret_unless_revealed(root: Path):
    store = root.parent / "home" / ".careeros" / "credentials.yaml"      # the default path under the temp HOME
    r = _cli(root, "creds", "set", "workday", "--username", "cand@example.com", "--notes", "acme tenant",
             "--password-stdin", stdin=SECRET + "\n")
    assert r.returncode == 0, r.stderr
    assert SECRET not in r.stdout + r.stderr
    assert stat.S_IMODE(store.stat().st_mode) == 0o600
    assert yaml.safe_load(store.read_text())["workday"]["password"] == SECRET
    r = _cli(root, "creds", "get", "workday")
    assert r.returncode == 0 and "cand@example.com" in r.stdout and SECRET not in r.stdout
    r = _cli(root, "creds", "get", "workday", "--json")
    got = json.loads(r.stdout)
    assert got == {"site": "workday", "username": "cand@example.com", "notes": "acme tenant", "has_password": True}
    r = _cli(root, "creds", "get", "workday", "--reveal")
    assert r.stdout == SECRET + "\n"
    r = _cli(root, "creds", "list")
    assert r.returncode == 0 and "workday" in r.stdout and SECRET not in r.stdout
    assert json.loads(_cli(root, "creds", "list", "--json").stdout)[0]["has_secret"] is True
    assert "PASS  credentials" in _cli(root, "doctor").stdout
    store.chmod(0o644)
    assert "WARN  credentials" in _cli(root, "doctor").stdout
    assert _cli(root, "creds", "rm", "workday").returncode == 0
    assert _cli(root, "creds", "get", "workday").returncode == 1
    assert _cli(root, "creds", "rm", "workday").returncode == 1


def test_creds_path_override_inside_the_repo_warns(root: Path):
    pipe_p = root / "config" / "pipeline.yaml"
    pipe = yaml.safe_load(pipe_p.read_text())
    pipe["paths"]["credentials"] = "secrets/credentials.yaml"
    pipe_p.write_text(yaml.safe_dump(pipe))
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    r = _cli(root, "creds", "set", "lever", "--username", "u", "--password-stdin", stdin="pw-12345\n")
    assert r.returncode == 0, r.stderr
    assert (root / "secrets" / "credentials.yaml").is_file()
    out = _cli(root, "doctor").stdout
    assert "WARN  credentials" in out and "not gitignored" in out
