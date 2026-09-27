"""`careeros sync` against a local bare "template" repo and a "private" clone in tmp (git subprocess, no network).
Git config is isolated: no global/system config, temp HOME, identity set per repo."""
from __future__ import annotations

import os
import re
import shutil
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


def test_pull_untracked_collision_leaves_user_on_base(repos, env):
    template_commit(repos, env, {"new.txt": "from template\n"}, "feat: add new.txt")
    priv = repos["private"]
    (priv / "new.txt").write_text("mine, untracked\n")
    r = cli(priv, env, "pull", "--no-checks")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "new.txt" in r.stderr and "Traceback" not in r.stderr
    assert git(priv, env, "branch", "--show-current").stdout.strip() == "main"
    assert "sync/" not in git(priv, env, "branch", "--list").stdout
    assert (priv / "new.txt").read_text() == "mine, untracked\n"


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


def test_hook_blocks_personal_path_in_history_even_if_deleted(repos, env):
    priv = repos["private"]
    assert cli(priv, env, "install-hook").returncode == 0
    git(priv, env, "switch", "-q", "-c", "fix/y", "template/main")
    commit(priv, env, {"personal/x.md": "secret\n"}, "add personal by mistake")
    git(priv, env, "rm", "-q", "personal/x.md")
    git(priv, env, "commit", "-q", "-m", "remove it again")
    r = git(priv, env, "push", "template", "fix/y", check=False)
    assert r.returncode != 0
    assert "BLOCKED" in r.stderr and "personal/x.md" in r.stderr
    assert git(repos["bare"], env, "branch", "--list", "fix/y").stdout.strip() == ""
    # the same history pushed by raw URL (no remote-tracking refs) is scanned in full: still blocked
    r = git(priv, env, "push", str(repos["bare"]), "fix/y", check=False)
    assert r.returncode != 0 and "BLOCKED" in r.stderr


def test_hook_blocks_committed_symlink_to_private_dir(repos, env):
    priv = repos["private"]
    assert cli(priv, env, "install-hook").returncode == 0
    git(priv, env, "switch", "-q", "-c", "fix/z", "template/main")
    (priv / "profile").symlink_to(priv / "personal")
    git(priv, env, "add", "profile")
    git(priv, env, "commit", "-q", "-m", "link profile")
    r = git(priv, env, "push", "template", "fix/z", check=False)
    assert r.returncode != 0 and "BLOCKED" in r.stderr and "profile" in r.stderr


@pytest.mark.parametrize("name", ["personal/CV \u2013 2026.pdf", "data/jobs/x/r\u00e9sum\u00e9.pdf",
                                  'profile/my "cv".pdf'])
def test_hook_blocks_non_ascii_and_quoted_personal_names(repos, env, name):
    priv = repos["private"]
    assert cli(priv, env, "install-hook").returncode == 0
    git(priv, env, "switch", "-q", "-c", "fix/q", "template/main")
    commit(priv, env, {name: "x\n"}, "add file")
    r = git(priv, env, "push", "template", "fix/q", check=False)
    assert r.returncode != 0 and "BLOCKED" in r.stderr
    assert name in r.stderr
    assert git(repos["bare"], env, "branch", "--list", "fix/q").stdout.strip() == ""


def test_status_in_sync_with_non_ascii_personal_file_and_kept_file(repos, env):
    priv = repos["private"]
    commit(priv, env, {"personal/CV \u2013 2026.pdf": "x\n", "docs/Notiz \u00fc.md": "mine\n",
                       ".template-sync-keep": "README.md  # private\ndocs/Notiz*  # private note\n"}, "more")
    r = cli(priv, env, "status")
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs ssh-keygen for ssh-signed commits")
def test_hook_blocks_history_with_signed_commits_and_show_signature(repos, env, tmp_path):
    priv = repos["private"]
    key = tmp_path / "signkey"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "test", "-f", str(key)], check=True,
                   env=env, capture_output=True, timeout=60)
    signers = tmp_path / "allowed_signers"
    signers.write_text("test@example.invalid " + (tmp_path / "signkey.pub").read_text())
    for k, v in (("gpg.format", "ssh"), ("user.signingkey", str(key)), ("commit.gpgsign", "true"),
                 ("gpg.ssh.allowedSignersFile", str(signers)), ("log.showSignature", "true")):
        git(priv, env, "config", k, v)
    assert cli(priv, env, "install-hook").returncode == 0
    git(priv, env, "switch", "-q", "-c", "fix/s", "template/main")
    commit(priv, env, {"personal/x.md": "secret\n"}, "signed: add personal")
    git(priv, env, "rm", "-q", "personal/x.md")
    git(priv, env, "commit", "-q", "-m", "signed: remove it")
    assert "signature" in git(priv, env, "log", "-1").stdout.lower()  # the setting is really active
    r = git(priv, env, "push", "template", "fix/s", check=False)
    assert r.returncode != 0 and "BLOCKED" in r.stderr and "personal/x.md" in r.stderr
    assert git(repos["bare"], env, "branch", "--list", "fix/s").stdout.strip() == ""


def test_hook_matches_template_url_case_insensitively(repos, env, tmp_path):
    priv = repos["private"]
    mixed = tmp_path / "other" / "Career-OS-Template.git"  # own dir: macOS tmp is case-insensitive
    git(tmp_path, env, "init", "-q", "--bare", "-b", "main", str(mixed))
    git(priv, env, "remote", "add", "tpl2", str(mixed))
    assert cli(priv, env, "install-hook").returncode == 0
    r = git(priv, env, "push", "tpl2", "HEAD:refs/heads/main", check=False)
    assert r.returncode != 0 and "BLOCKED" in r.stderr
    assert git(mixed, env, "branch", "--list").stdout.strip() == ""


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


def test_hook_scans_full_history_when_remote_also_pushes_elsewhere(repos, env):
    # origin pushes to the private copy AND the template: its tracking refs must not hide history from the scan
    priv = repos["private"]
    assert cli(priv, env, "install-hook").returncode == 0
    git(priv, env, "switch", "-q", "-c", "fix/h", "template/main")
    commit(priv, env, {"personal/a.md": "secret\n"}, "add personal by mistake")
    git(priv, env, "rm", "-q", "personal/a.md")
    git(priv, env, "commit", "-q", "-m", "remove it again")
    assert git(priv, env, "push", "origin", "fix/h", check=False).returncode == 0  # private only: allowed
    git(priv, env, "remote", "set-url", "--add", "--push", "origin", str(repos["origin"]))
    git(priv, env, "remote", "set-url", "--add", "--push", "origin", str(repos["bare"]))
    r = git(priv, env, "push", "origin", "fix/h", check=False)
    assert r.returncode != 0 and "BLOCKED" in r.stderr and "personal/a.md" in r.stderr
    assert git(repos["bare"], env, "branch", "--list", "fix/h").stdout.strip() == ""


@pytest.mark.parametrize("nested", ["name", "refspec"])
def test_hook_scans_full_history_when_another_remote_writes_under_differently_cased_template_refs(
        repos, env, tmp_path, nested):
    # on a case-insensitive filesystem (APFS) refs/remotes/Template/* resolves into refs/remotes/template/*, so a
    # remote named Template, or a refspec writing there, must not hide personal history from the scan either
    priv = repos["private"]
    assert cli(priv, env, "install-hook").returncode == 0
    side = tmp_path / "side.git"
    git(tmp_path, env, "init", "-q", "--bare", "-b", "main", str(side))
    if nested == "name":
        git(priv, env, "config", "remote.Template.url", str(side))
        git(priv, env, "config", "remote.Template.fetch", "+refs/heads/*:refs/remotes/Template/*")
    else:
        git(priv, env, "remote", "add", "side", str(side))
        git(priv, env, "config", "--replace-all", "remote.side.fetch", "+refs/heads/*:refs/remotes/Template/bak/*")
    git(priv, env, "switch", "-q", "-c", "leak", "template/main")
    commit(priv, env, {"personal/b.md": "secret\n"}, "add personal by mistake")
    git(priv, env, "rm", "-q", "personal/b.md")
    git(priv, env, "commit", "-q", "-m", "remove it again")
    git(priv, env, "push", "-q", str(side), "leak")
    git(priv, env, "fetch", "-q", "Template" if nested == "name" else "side")
    r = git(priv, env, "push", "template", "leak", check=False)
    assert r.returncode != 0 and "BLOCKED" in r.stderr and "personal/b.md" in r.stderr
    assert git(repos["bare"], env, "branch", "--list", "leak").stdout.strip() == ""


@pytest.mark.parametrize("nested", ["name", "refspec"])
def test_hook_scans_full_history_when_another_remote_writes_under_template_refs(repos, env, tmp_path, nested):
    # a remote named template/bak, or one whose fetch refspec writes under refs/remotes/template/, must not hide personal history from the scan
    priv = repos["private"]
    assert cli(priv, env, "install-hook").returncode == 0
    side = tmp_path / "side.git"
    git(tmp_path, env, "init", "-q", "--bare", "-b", "main", str(side))
    if nested == "name":
        # newer git refuses `remote add template/bak`, but older git and hand-edited config still allow it
        git(priv, env, "config", "remote.template/bak.url", str(side))
        git(priv, env, "config", "remote.template/bak.fetch", "+refs/heads/*:refs/remotes/template/bak/*")
    else:
        git(priv, env, "remote", "add", "side", str(side))
        git(priv, env, "config", "--replace-all", "remote.side.fetch", "+refs/heads/*:refs/remotes/template/bak/*")
    git(priv, env, "switch", "-q", "-c", "leak", "template/main")
    commit(priv, env, {"personal/b.md": "secret\n"}, "add personal by mistake")
    git(priv, env, "rm", "-q", "personal/b.md")
    git(priv, env, "commit", "-q", "-m", "remove it again")
    git(priv, env, "push", "-q", str(side), "leak")
    git(priv, env, "fetch", "-q", "template/bak" if nested == "name" else "side")
    assert git(priv, env, "rev-parse", "refs/remotes/template/bak/leak").returncode == 0
    r = git(priv, env, "push", "template", "leak", check=False)
    assert r.returncode != 0 and "BLOCKED" in r.stderr and "personal/b.md" in r.stderr
    assert git(repos["bare"], env, "branch", "--list", "leak").stdout.strip() == ""


@pytest.mark.parametrize("how", ["unqualified_dst", "legacy_remotes_file"])
def test_hook_scans_full_history_when_template_refs_are_written_by_unusual_fetch_rules(repos, env, tmp_path, how):
    # git expands an unqualified refspec dst (remotes/template/x -> refs/remotes/template/x), and legacy
    # .git/remotes/<name> files carry `Pull:` rules that git config never shows: neither may hide history
    priv = repos["private"]
    assert cli(priv, env, "install-hook").returncode == 0
    side = tmp_path / "side.git"
    git(tmp_path, env, "init", "-q", "--bare", "-b", "main", str(side))
    git(priv, env, "switch", "-q", "-c", "leak", "template/main")
    commit(priv, env, {"personal/b.md": "secret\n"}, "add personal by mistake")
    git(priv, env, "rm", "-q", "personal/b.md")
    git(priv, env, "commit", "-q", "-m", "remove it again")
    git(priv, env, "push", "-q", str(side), "leak:main")
    if how == "unqualified_dst":
        git(priv, env, "remote", "add", "side", str(side))
        git(priv, env, "config", "--replace-all", "remote.side.fetch", "refs/heads/main:remotes/template/leak")
    else:
        common = Path(git(priv, env, "rev-parse", "--git-common-dir").stdout.strip())
        common = common if common.is_absolute() else priv / common
        (common / "remotes").mkdir(exist_ok=True)
        (common / "remotes" / "side").write_text(f"URL: {side}\nPull: refs/heads/main:refs/remotes/template/leak\n")
    git(priv, env, "fetch", "-q", "side")
    assert git(priv, env, "rev-parse", "refs/remotes/template/leak").returncode == 0
    r = git(priv, env, "push", "template", "leak", check=False)
    assert r.returncode != 0 and "BLOCKED" in r.stderr and "personal/b.md" in r.stderr
    assert git(repos["bare"], env, "branch", "--list", "leak").stdout.strip() == ""


def _leak_branch(priv, env, side, name="personal/b.md"):
    """A `leak` branch off template/main whose history adds then removes a personal file, pushed to `side`."""
    git(priv, env, "switch", "-q", "-c", "leak", "template/main")
    commit(priv, env, {name: "secret\n"}, "add personal by mistake")
    git(priv, env, "rm", "-q", name)
    git(priv, env, "commit", "-q", "-m", "remove it again")
    git(priv, env, "push", "-q", str(side), "leak:main")


@pytest.mark.parametrize("how", ["update_ref", "fetch_url_refspec", "one_off_config", "include_if_onbranch",
                                 "worktree_config"])
def test_hook_blocks_history_behind_planted_template_tracking_refs(repos, env, tmp_path, how):
    # the guard asks the template itself (ls-remote) what it already has; a local refs/remotes/template/* ref,
    # however it was written, never hides history from the scan
    priv = repos["private"]
    assert cli(priv, env, "install-hook").returncode == 0
    side = tmp_path / "side.git"
    git(tmp_path, env, "init", "-q", "--bare", "-b", "main", str(side))
    _leak_branch(priv, env, side)
    dst = "refs/remotes/template/leak"
    if how == "update_ref":
        git(priv, env, "update-ref", dst, "leak")
    elif how == "fetch_url_refspec":
        git(priv, env, "fetch", "-q", str(side), f"main:{dst}")
    elif how == "one_off_config":
        git(priv, env, "-c", f"remote.o.url={side}", "-c", f"remote.o.fetch=refs/heads/main:{dst}", "fetch", "-q", "o")
    elif how == "include_if_onbranch":
        inc = tmp_path / "inc.cfg"
        inc.write_text(f'[remote "o"]\n\turl = {side}\n\tfetch = refs/heads/main:{dst}\n')
        git(priv, env, "config", "includeIf.onbranch:tmp-*.path", str(inc))
        git(priv, env, "switch", "-q", "-c", "tmp-x")
        git(priv, env, "fetch", "-q", "o")
        git(priv, env, "switch", "-q", "leak")
    else:
        git(priv, env, "config", "extensions.worktreeConfig", "true")
        wt = tmp_path / "wt"
        git(priv, env, "worktree", "add", "-q", "--detach", str(wt))
        git(wt, env, "config", "--worktree", "remote.o.url", str(side))
        git(wt, env, "config", "--worktree", "remote.o.fetch", f"refs/heads/main:{dst}")
        git(wt, env, "fetch", "-q", "o")
    assert git(priv, env, "rev-parse", dst).stdout.strip() == git(priv, env, "rev-parse", "leak").stdout.strip()
    r = git(priv, env, "push", "template", "leak", check=False)
    assert r.returncode != 0 and "BLOCKED" in r.stderr and "personal/b.md" in r.stderr
    assert git(repos["bare"], env, "branch", "--list", "leak").stdout.strip() == ""


def test_hook_skips_history_the_template_already_has(repos, env, tmp_path):
    # template history that itself touched a personal-looking path is excluded via the template's real tips
    template_commit(repos, env, {"data/sample.txt": "x\n"}, "add sample")
    git(repos["upstream"], env, "rm", "-q", "data/sample.txt")
    git(repos["upstream"], env, "commit", "-q", "-m", "drop sample")
    git(repos["upstream"], env, "push", "-q", "origin", "main")
    priv = repos["private"]
    assert cli(priv, env, "install-hook").returncode == 0
    git(priv, env, "fetch", "-q", "template")
    git(priv, env, "switch", "-q", "-c", "fix/z", "template/main")
    commit(priv, env, {"src/app.py": "VALUE = 3\n"}, "fix: value")
    git(priv, env, "update-ref", "-d", "refs/remotes/template/main")  # no local tracking refs needed
    r = git(priv, env, "push", "template", "fix/z", check=False)
    assert r.returncode == 0, r.stderr
    # when the template can't be asked (ls-remote fails), the whole history is scanned: fail safe
    sha = git(priv, env, "rev-parse", "HEAD").stdout.strip()
    missing = tmp_path / "career-os-template-missing.git"
    r = cli(priv, env, "check-template-push", "x", str(missing), stdin=f"refs/heads/fix/z {sha} refs/heads/fix/z {'0' * 40}\n")
    assert r.returncode == 1 and "data/sample.txt" in r.stderr


def test_hook_empty_pattern_config_falls_back_to_default(repos, env):
    priv = repos["private"]
    assert cli(priv, env, "install-hook").returncode == 0
    git(priv, env, "config", "careeros.templateUrlPattern", "")
    r = git(priv, env, "push", "template", "HEAD:refs/heads/leak", check=False)
    assert r.returncode != 0 and "BLOCKED" in r.stderr
    assert git(repos["bare"], env, "branch", "--list", "leak").stdout.strip() == ""


def test_status_reads_keep_file_from_head_not_working_tree(repos, env):
    priv = repos["private"]
    commit(priv, env, {"src/app.py": "VALUE = 99\n"}, "code change")
    (priv / ".template-sync-keep").write_text("README.md  # private\nsrc/app.py  # uncommitted\n")
    r = cli(priv, env, "status")
    assert r.returncode == 2 and "src/app.py" in r.stdout, r.stdout + r.stderr


def test_hook_scans_full_history_when_ls_remote_would_rewrite_the_push_url_to_another_repo(repos, env, tmp_path):
    # git hands the hook the URL after pushInsteadOf; ls-remote applies insteadOf again, so a global rule can point
    # it at a mirror that already has the leak branch: its tips must not be excluded, the full history is scanned
    priv = repos["private"]
    assert cli(priv, env, "install-hook").returncode == 0
    mirror = tmp_path / "mirror.git"
    git(tmp_path, env, "init", "-q", "--bare", "-b", "main", str(mirror))
    git(priv, env, "switch", "-q", "-c", "leak", "template/main")
    commit(priv, env, {"personal/c.md": "secret\n"}, "add personal by mistake")
    git(priv, env, "rm", "-q", "personal/c.md")
    git(priv, env, "commit", "-q", "-m", "remove it again")
    git(priv, env, "push", "-q", str(mirror), "leak")
    t = str(repos["bare"])
    git(tmp_path, env, "config", "--global", f"url.{t}.pushInsteadOf", "tmpl:")
    git(tmp_path, env, "config", "--global", f"url.{mirror}.insteadOf", t)
    git(priv, env, "remote", "add", "tmpl", "tmpl:")
    r = git(priv, env, "push", "tmpl", "leak", check=False)
    assert r.returncode != 0 and "BLOCKED" in r.stderr and "personal/c.md" in r.stderr
    assert git(repos["bare"], env, "branch", "--list", "leak").stdout.strip() == ""
