"""careeros.sync pure helpers: drift with personal paths + keep globs, branch naming, hook pattern, hook file."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from careeros import sync

pytestmark = pytest.mark.unit

PERSONAL = sync.DEFAULT_PERSONAL_PATHS


def test_default_personal_paths():
    assert set(PERSONAL) == {"personal/", "profile/", "config/", "CLAUDE.local.md", "data/"}


@pytest.mark.parametrize("path,expected", [
    ("personal/notes.md", True),
    ("profile/master.yaml", True),
    ("config/pipeline.yaml", True),
    ("data/jobs/x/status.json", True),
    ("CLAUDE.local.md", True),
    ("CLAUDE.md", False),
    ("src/careeros/config.py", False),
    ("examples/config/pipeline.yaml", False),
    ("personalities.md", False),
    ("profile", True),       # a committed symlink to the private dir
    ("data", True),
    ("personal", True),
    ("config", True),
    ("profiles/x", False),
])
def test_is_personal(path, expected):
    assert sync.is_personal(path, PERSONAL) is expected


def test_parse_personal_paths_from_git_config_value():
    assert sync.parse_personal_paths(None) == PERSONAL
    assert sync.parse_personal_paths("") == PERSONAL
    assert sync.parse_personal_paths("private/, secrets.txt  notes/") == ("private/", "secrets.txt", "notes/")


def test_parse_keep_strips_comments_and_blanks():
    text = """# files this private copy keeps different on purpose
README.md            # my own README
.gitattributes  # LFS rules for my data

docs/private-*.md
"""
    assert sync.parse_keep(text) == ["README.md", ".gitattributes", "docs/private-*.md"]


@pytest.mark.parametrize("path,globs,expected", [
    ("README.md", ["README.md"], True),
    ("docs/README.md", ["README.md"], False),
    ("docs/private-plan.md", ["docs/private-*.md"], True),
    ("notes/a/b.txt", ["notes/"], True),
    ("notes2/b.txt", ["notes/"], False),
    ("src/x.py", [], False),
])
def test_matches_keep(path, globs, expected):
    assert sync.matches_keep(path, globs) is expected


def test_compute_drift_excludes_personal_keep_and_the_keep_file():
    changed = ["README.md", ".gitattributes", "personal/profile/master.yaml", "CLAUDE.local.md",
               "src/careeros/cli.py", sync.KEEP_FILE, "docs/GETTING_STARTED.md"]
    drift = sync.compute_drift(changed, PERSONAL, ["README.md", ".gitattributes"])
    assert drift == ["docs/GETTING_STARTED.md", "src/careeros/cli.py"]


def test_status_exit_code_drift_wins_over_behind():
    assert sync.status_exit_code(behind=0, drift=0) == sync.EXIT_IN_SYNC == 0
    assert sync.status_exit_code(behind=3, drift=0) == sync.EXIT_BEHIND == 1
    assert sync.status_exit_code(behind=0, drift=1) == sync.EXIT_DRIFT == 2
    assert sync.status_exit_code(behind=3, drift=1) == sync.EXIT_DRIFT


def test_sync_branch_name_dated_and_unique():
    d = date(2026, 3, 4)
    assert sync.sync_branch_name(d, set()) == "sync/2026-03-04"
    assert sync.sync_branch_name(d, {"sync/2026-03-04"}) == "sync/2026-03-04-2"
    assert sync.sync_branch_name(d, {"sync/2026-03-04", "sync/2026-03-04-2"}) == "sync/2026-03-04-3"


@pytest.mark.parametrize("url,pattern,expected", [
    ("git@github.com:someone/career-os-template.git", sync.DEFAULT_URL_PATTERN, True),
    ("https://github.com/someone/career-os-template", sync.DEFAULT_URL_PATTERN, True),
    ("/tmp/x/career-os-template.git", sync.DEFAULT_URL_PATTERN, True),
    ("git@github.com:someone/career-os.git", sync.DEFAULT_URL_PATTERN, False),
    ("git@example.com:me/public-fork.git", "*public-fork*", True),
])
def test_url_matches(url, pattern, expected):
    assert sync.url_matches(url, pattern) is expected


def test_blocked_paths():
    files = ["README.md", "personal/a.md", "src/x.py", "CLAUDE.local.md", "config/pipeline.yaml"]
    assert sync.blocked_paths(files, PERSONAL) == ["personal/a.md", "CLAUDE.local.md", "config/pipeline.yaml"]
    assert sync.blocked_paths(["README.md"], PERSONAL) == []


def test_hook_script_has_marker_pattern_and_quoted_python():
    s = sync.hook_script("/opt/my env/bin/python")
    assert s.startswith("#!/bin/sh\n")
    assert sync.HOOK_MARKER in s
    assert "careeros.templateUrlPattern" in s and sync.DEFAULT_URL_PATTERN in s
    assert "'/opt/my env/bin/python'" in s
    assert "sync check-template-push" in s


def test_install_hook_new_idempotent_foreign_and_force(tmp_path: Path):
    hook = tmp_path / "hooks" / "pre-push"
    assert sync.install_hook(hook, "/usr/bin/python3") == "installed"
    assert hook.stat().st_mode & 0o111
    assert sync.install_hook(hook, "/usr/bin/python3") == "unchanged"
    assert sync.install_hook(hook, "/other/python") == "updated"

    hook.write_text("#!/bin/sh\necho mine\n")
    with pytest.raises(sync.HookExists):
        sync.install_hook(hook, "/usr/bin/python3")
    assert hook.read_text() == "#!/bin/sh\necho mine\n"
    assert sync.install_hook(hook, "/usr/bin/python3", force=True) == "replaced"
    assert (tmp_path / "hooks" / "pre-push.bak").read_text() == "#!/bin/sh\necho mine\n"
    assert sync.HOOK_MARKER in hook.read_text()


def test_pr_command_quotes_body_and_names_branch():
    cmd = sync.pr_command(branch="sync/2026-03-04", base="main", remote="template", template_branch="main",
                          commits=["abc123 feat: thing"], results=[("pytest", "passed"), ("ui", "skipped")])
    assert cmd.startswith("gh pr create --base main --head sync/2026-03-04 ")
    assert "--title 'sync: merge template/main (2026-03-04)'" in cmd
    assert "pytest: passed" in cmd and "ui: skipped" in cmd and "abc123 feat: thing" in cmd


def test_check_plan_uses_repo_venv_and_ui_when_present(tmp_path: Path):
    plan = sync.check_plan(tmp_path, fallback_python="/usr/bin/python3")
    assert [name for name, _, _ in plan] == ["pytest"]
    assert plan[0][1] == ["/usr/bin/python3", "-m", "pytest", "-q"]

    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "python").write_text("")
    (tmp_path / "ui").mkdir()
    (tmp_path / "ui" / "package.json").write_text("{}")
    plan = sync.check_plan(tmp_path, fallback_python="/usr/bin/python3")
    assert [name for name, _, _ in plan] == ["pytest", "npm ci", "npm test", "npm run build"]
    assert plan[0][1][0] == str(tmp_path / ".venv" / "bin" / "python")
    assert plan[2][1] == ["npm", "test", "--", "--run"]
    assert plan[3][2] == tmp_path / "ui"


@pytest.mark.parametrize("path", ["Personal/notes.md", "PROFILE/master.yaml", "claude.local.md", "Data", "Config/x"])
def test_is_personal_case_insensitive(path):
    assert sync.is_personal(path, PERSONAL) is True


class _FakeGit(sync.Git):
    """Answers git calls from a table keyed by the first arg; asserts path reads use -z."""

    def __init__(self, outputs: dict[str, str]):
        super().__init__(Path("."))
        self.outputs = outputs
        self.calls: list = []

    def run(self, *args, check=True, input=None):
        import subprocess as sp

        if args[0] in ("ls-tree", "diff", "diff-tree"):
            assert "-z" in args, args
        self.calls.append((args, input))
        return sp.CompletedProcess(["git", *args], 0, self.outputs.get(args[0], ""), "")


def test_pushed_paths_reads_nul_separated_unquoted_names():
    g = _FakeGit({"rev-list": "c1\n", "diff-tree": "src/a.py\0personal/résumé.md\0",
                  "ls-tree": "src/a.py\0profile/my \"cv\".pdf\0", "rev-parse": ""})
    got = sync.pushed_paths(g, "template", "a" * 40, sync.ZERO_SHA)
    assert got == {"src/a.py", "personal/résumé.md", 'profile/my "cv".pdf'}
    assert sync.blocked_paths(sorted(got), PERSONAL) == ["personal/résumé.md", 'profile/my "cv".pdf']


def test_keep_globs_match_unquoted_non_ascii_names():
    assert sync.compute_drift(["docs/Lebenslauf – alt.md", "src/ü.py"], PERSONAL, ["docs/Lebenslauf*"]) == ["src/ü.py"]


def test_pushed_paths_uses_plumbing_not_log_so_signatures_cannot_corrupt_paths():
    # log.showSignature=true makes porcelain `git log -z` prepend signature text without a NUL
    sig = 'Good "git" signature for test@example.invalid with ED25519 key SHA256:abc\n'
    g = _FakeGit({"log": sig + "personal/cv.md\0src/a.py\0", "rev-list": "c1\nc2\n",
                  "diff-tree": "personal/cv.md\0src/a.py\0", "ls-tree": "src/a.py\0", "rev-parse": ""})
    got = sync.pushed_paths(g, "template", "a" * 40, sync.ZERO_SHA)
    assert got == {"personal/cv.md", "src/a.py"}
    assert sync.blocked_paths(sorted(got), PERSONAL) == ["personal/cv.md"]
    dt = [(a, i) for a, i in g.calls if a[0] == "diff-tree"]
    assert dt and "--stdin" in dt[0][0] and "--root" in dt[0][0] and "-m" in dt[0][0]
    assert dt[0][1].split() == ["c1", "c2"]


def test_git_runs_with_output_neutralising_overrides():
    for flag in ("core.quotePath=false", "color.ui=never", "log.showSignature=false"):
        assert flag in sync.GIT_OVERRIDES


@pytest.mark.parametrize("url", ["git@github.com:Someone/Career-OS-Template.git", "/tmp/CAREER-OS-TEMPLATE.git"])
def test_url_matches_case_insensitive(url):
    assert sync.url_matches(url, sync.DEFAULT_URL_PATTERN) is True
    assert sync.url_matches(url.lower(), "*Career-OS-Template*") is True


def test_hook_script_lowercases_url_and_pattern():
    s = sync.hook_script("/usr/bin/python3")
    assert "tr '[:upper:]' '[:lower:]'" in s


@pytest.mark.parametrize("path,entries", [
    ("personal/x.md", ("./personal/",)),
    ("personal/x.md", ("/personal/",)),
    ("./personal/x.md", ("personal/",)),
    ("perso\u0308nlich/x.md", ("pers\u00f6nlich/",)),   # NFD path vs NFC entry
    ("pers\u00f6nlich/x.md", ("perso\u0308nlich/",)),   # NFC path vs NFD entry
])
def test_is_personal_normalises_entries_and_paths(path, entries):
    assert sync.is_personal(path, sync.parse_personal_paths(" ".join(entries))) is True
