"""`careeros init` and the "run careeros init" guard, as subprocesses on a temp checkout."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import EXAMPLE_REPO, PY, subprocess_env

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


def _cli(root: Path, home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), *args], capture_output=True, text=True,
                          env=subprocess_env(root, home), timeout=120)


def test_commands_before_init_say_run_init(checkout: Path, home: Path):
    for args in (("stats",), ("jobs", "list"), ("tracker", "applied-count", "Acme")):
        r = _cli(checkout, home, *args)
        assert r.returncode == 1, args
        assert "careeros init" in r.stderr and "Traceback" not in r.stderr, args


def test_init_copies_examples_then_everything_runs(checkout: Path, home: Path):
    r = _cli(checkout, home, "init")
    assert r.returncode == 0, r.stderr
    assert "copied    config/" in r.stdout and "copied    profile/" in r.stdout
    for hint in ("profile/master.yaml", "profile/standard_answers.yaml", "profile/confidential_terms.yaml",
                 "config/targets.yaml", "config/companies.yaml"):
        assert hint in r.stdout, hint
    assert (checkout / "profile" / "master.yaml").is_file() and (checkout / "config" / "pipeline.yaml").is_file()

    (checkout / "profile" / "master.yaml").write_text((checkout / "profile" / "master.yaml").read_text()
                                                     .replace("Alex Example", "Sam Candidate"))
    again = _cli(checkout, home, "init")
    assert again.returncode == 0 and "kept      profile/" in again.stdout and "nothing copied" in again.stdout
    assert "Sam Candidate" in (checkout / "profile" / "master.yaml").read_text()  # never overwritten

    st = _cli(checkout, home, "stats")
    assert st.returncode == 0, st.stderr
    assert "jobs in data: 0" in st.stdout
    assert f"not created ({checkout.resolve() / 'data' / 'JobTracker.xlsx'})" in st.stdout  # default tracker path
    assert not any(home.iterdir())


def test_init_link_points_personal_dirs_at_private_repo(checkout: Path, home: Path, tmp_path: Path):
    private = tmp_path / "my-private-career"
    shutil.copytree(EXAMPLE_REPO / "config", private / "config")
    shutil.copytree(EXAMPLE_REPO / "profile", private / "profile")
    (private / "CLAUDE.local.md").write_text("# notes\n")

    r = _cli(checkout, home, "init", "--link", str(private))
    assert r.returncode == 0, r.stderr
    for name in ("profile", "config", "CLAUDE.local.md"):
        assert (checkout / name).is_symlink() and (checkout / name).resolve() == (private / name).resolve()
    assert _cli(checkout, home, "jobs", "list").returncode == 0
    assert _cli(checkout, home, "init", "--link", str(private)).returncode == 0  # idempotent


def test_init_link_refuses_real_dir(checkout: Path, home: Path, tmp_path: Path):
    assert _cli(checkout, home, "init").returncode == 0  # real copied dirs
    private = tmp_path / "priv"
    shutil.copytree(EXAMPLE_REPO / "config", private / "config")
    shutil.copytree(EXAMPLE_REPO / "profile", private / "profile")
    r = _cli(checkout, home, "init", "--link", str(private))
    assert r.returncode == 1
    assert "refusing to replace real" in r.stderr
    assert not (checkout / "profile").is_symlink() and not (checkout / "config").is_symlink()
