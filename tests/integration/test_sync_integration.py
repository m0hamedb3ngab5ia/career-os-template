"""`careeros sync` against a local bare "template" repo and a "private" clone in tmp (git subprocess, no network).
Git config is isolated: no global/system config, temp HOME, identity set per repo."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
from conftest import PY, ROOT

pytestmark = pytest.mark.integration


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir()
    (home / "gitconfig").write_text("")
    e = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    e.update({
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": str(home / "gitconfig"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), e.get("PYTHONPATH", "")]).rstrip(os.pathsep),
    })
    return e


def git(cwd: Path, env: dict, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
    if check and r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {r.stdout}{r.stderr}")
    return r


def ident(repo: Path, env: dict) -> None:
    git(repo, env, "config", "user.name", "Test User")
    git(repo, env, "config", "user.email", "test@example.invalid")


def commit(repo: Path, env: dict, files: dict[str, str], msg: str) -> None:
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    git(repo, env, "add", "-A")
    git(repo, env, "commit", "-q", "-m", msg)


def cli(repo: Path, env: dict, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "careeros.cli", "sync", *args], cwd=repo, env=env, input=stdin,
                          capture_output=True, text=True, timeout=300)


@pytest.fixture
def repos(tmp_path: Path, env: dict) -> dict[str, Path]:
    """template.git (bare, URL matches the default pattern), upstream (a template working clone),
    private (clone with remote `template` + its own bare `origin`, personal/ committed, README kept)."""
    bare = tmp_path / "career-os-template.git"
    git(tmp_path, env, "init", "-q", "--bare", "-b", "main", str(bare))
    up = tmp_path / "upstream"
    git(tmp_path, env, "clone", "-q", str(bare), str(up))
    ident(up, env)
    git(up, env, "switch", "-q", "-c", "main")
    commit(up, env, {"README.md": "template readme\n", "src/app.py": "VALUE = 1\n",
                     "tests/test_ok.py": "def test_ok():\n    assert True\n"}, "initial")
    git(up, env, "push", "-q", "origin", "main")

    priv = tmp_path / "private"
    git(tmp_path, env, "clone", "-q", "-o", "template", str(bare), str(priv))
    ident(priv, env)
    origin = tmp_path / "private-origin.git"
    git(tmp_path, env, "init", "-q", "--bare", "-b", "main", str(origin))
    git(priv, env, "remote", "add", "origin", str(origin))
    commit(priv, env, {"personal/notes.md": "private notes\n", "README.md": "my own readme\n",
                       ".template-sync-keep": "README.md   # private README\n"}, "personal data")
    return {"bare": bare, "upstream": up, "private": priv, "origin": origin}


def template_commit(repos, env, files, msg):
    commit(repos["upstream"], env, files, msg)
    git(repos["upstream"], env, "push", "-q", "origin", "main")


# --- status -------------------------------------------------------------------------------------------------

def test_status_in_sync(repos, env):
    r = cli(repos["private"], env, "status")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "in sync" in r.stdout


def test_status_behind_lists_template_commits(repos, env):
    template_commit(repos, env, {"src/app.py": "VALUE = 2\n"}, "feat: bump value")
    r = cli(repos["private"], env, "status")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "feat: bump value" in r.stdout


def test_status_drift_lists_non_personal_non_kept_files(repos, env):
    commit(repos["private"], env, {"src/app.py": "VALUE = 99\n", "personal/more.md": "x\n"}, "oops, code change")
    r = cli(repos["private"], env, "status")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "src/app.py" in r.stdout
    assert "README.md" not in r.stdout and "personal/" not in r.stdout


def test_status_custom_remote_name(repos, env):
    git(repos["private"], env, "remote", "rename", "template", "upstream-tpl")
    assert cli(repos["private"], env, "status", "--remote", "upstream-tpl").returncode == 0
    r = cli(repos["private"], env, "status")
    assert r.returncode != 0 and "template" in r.stderr and "Traceback" not in r.stderr


# --- pull ---------------------------------------------------------------------------------------------------

def test_pull_merges_on_a_dated_sync_branch(repos, env):
    template_commit(repos, env, {"src/app.py": "VALUE = 2\n"}, "feat: bump value")
    priv = repos["private"]
    r = cli(priv, env, "pull", "--no-checks")
    assert r.returncode == 0, r.stdout + r.stderr
    branch = git(priv, env, "branch", "--show-current").stdout.strip()
    assert re.fullmatch(r"sync/\d{4}-\d{2}-\d{2}", branch)
    parents = git(priv, env, "rev-list", "--parents", "-n1", "HEAD").stdout.split()
    assert len(parents) == 3  # a real merge commit (no fast-forward)
    assert (priv / "src/app.py").read_text() == "VALUE = 2\n"
    assert (priv / "README.md").read_text() == "my own readme\n"
    assert "gh pr create --base main --head " + branch in r.stdout
    assert "git push -u origin " + branch in r.stdout
    assert cli(priv, env, "status").returncode == 0


def test_pull_named_branch_and_up_to_date(repos, env):
    priv = repos["private"]
    r = cli(priv, env, "pull", "--no-checks")
    assert r.returncode == 0 and "up to date" in r.stdout
    assert git(priv, env, "branch", "--show-current").stdout.strip() == "main"
    template_commit(repos, env, {"docs/new.md": "hi\n"}, "docs: new")
    r = cli(priv, env, "pull", "--no-checks", "--branch", "sync/docs-new")
    assert r.returncode == 0, r.stdout + r.stderr
    assert git(priv, env, "branch", "--show-current").stdout.strip() == "sync/docs-new"


def test_pull_refuses_dirty_tree(repos, env):
    template_commit(repos, env, {"src/app.py": "VALUE = 2\n"}, "feat: bump value")
    priv = repos["private"]
    (priv / "src/app.py").write_text("VALUE = 5\n")
    r = cli(priv, env, "pull", "--no-checks")
    assert r.returncode == 1
    assert "uncommitted" in r.stderr
    assert "sync/" not in git(priv, env, "branch", "--list").stdout


def test_pull_stops_cleanly_on_conflict(repos, env):
    template_commit(repos, env, {"src/app.py": "VALUE = 2\n"}, "feat: bump value")
    priv = repos["private"]
    commit(priv, env, {"src/app.py": "VALUE = 3\n"}, "local edit")
    r = cli(priv, env, "pull", "--no-checks")
    assert r.returncode == 3, r.stdout + r.stderr
    out = r.stdout + r.stderr
    assert "src/app.py" in out and "git merge --abort" in out and "git commit --no-edit" in out
    assert "Traceback" not in out
    assert git(priv, env, "diff", "--name-only", "--diff-filter=U").stdout.strip() == "src/app.py"


def test_pull_runs_local_checks_and_reports_them(repos, env):
    template_commit(repos, env, {"docs/new.md": "hi\n"}, "docs: new")
    r = cli(repos["private"], env, "pull")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "pytest: passed" in r.stdout
    assert "gh pr create" in r.stdout


def test_pull_failing_checks_exit_1_without_pr_command(repos, env):
    template_commit(repos, env, {"tests/test_bad.py": "def test_bad():\n    assert False\n"}, "test: bad")
    r = cli(repos["private"], env, "pull")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "pytest: failed" in r.stdout
    assert "gh pr create" not in r.stdout


# --- pre-push guard -----------------------------------------------------------------------------------------

def test_install_hook_idempotent_and_respects_foreign_hook(repos, env):
    priv = repos["private"]
    hook = priv / ".git" / "hooks" / "pre-push"
    r = cli(priv, env, "install-hook")
    assert r.returncode == 0 and "installed" in r.stdout
    assert "unchanged" in cli(priv, env, "install-hook").stdout
    hook.write_text("#!/bin/sh\nexit 0\n")
    r = cli(priv, env, "install-hook")
    assert r.returncode == 1 and "--force" in r.stderr
    assert hook.read_text() == "#!/bin/sh\nexit 0\n"
    r = cli(priv, env, "install-hook", "--force")
    assert r.returncode == 0 and (hook.parent / "pre-push.bak").exists()


def test_hook_blocks_personal_push_to_template_and_allows_others(repos, env):
    priv = repos["private"]
    assert cli(priv, env, "install-hook").returncode == 0

    r = git(priv, env, "push", "template", "HEAD:refs/heads/leak", check=False)
    assert r.returncode != 0
    assert "BLOCKED" in r.stderr and "personal/notes.md" in r.stderr
    assert git(repos["bare"], env, "branch", "--list", "leak").stdout.strip() == ""

    # the private remote gets everything
    assert git(priv, env, "push", "origin", "HEAD:refs/heads/main", check=False).returncode == 0

    # clean template work (branched from template/main) is allowed
    git(priv, env, "switch", "-q", "-c", "fix/x", "template/main")
    commit(priv, env, {"src/app.py": "VALUE = 7\n"}, "fix: value")
    r = git(priv, env, "push", "template", "fix/x", check=False)
    assert r.returncode == 0, r.stderr


def test_hook_pattern_and_personal_paths_from_git_config(repos, env):
    priv = repos["private"]
    assert cli(priv, env, "install-hook").returncode == 0
    git(priv, env, "config", "careeros.templateUrlPattern", "*private-origin*")
    r = git(priv, env, "push", "origin", "HEAD:refs/heads/main", check=False)
    assert r.returncode != 0 and "BLOCKED" in r.stderr

    git(priv, env, "config", "careeros.personalPaths", "secret/")
    assert git(priv, env, "push", "origin", "HEAD:refs/heads/main", check=False).returncode == 0


def test_check_template_push_directly(repos, env):
    priv = repos["private"]
    sha = git(priv, env, "rev-parse", "HEAD").stdout.strip()
    zero = "0" * 40
    line = f"refs/heads/main {sha} refs/heads/main {zero}\n"
    url = str(repos["bare"])
    r = cli(priv, env, "check-template-push", "template", url, stdin=line)
    assert r.returncode == 1 and "personal/notes.md" in r.stderr
    assert cli(priv, env, "check-template-push", "origin", str(repos["origin"]), stdin=line).returncode == 0
    delete = f"(delete) {zero} refs/heads/old {sha}\n"
    assert cli(priv, env, "check-template-push", "template", url, stdin=delete).returncode == 0
