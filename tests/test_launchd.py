"""LaunchAgent plist + launchctl calls, written to a tmp dir with launchctl injected (never the real one)."""
from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from careeros.runs.launchd import build_plist, install, status, uninstall

pytestmark = pytest.mark.unit


class FakeLaunchctl:
    def __init__(self, loaded=False):
        self.calls, self.loaded = [], loaded

    def __call__(self, args):
        self.calls.append(args)
        if args[0] == "print":
            return (0 if self.loaded else 113), "", ""
        if args[0] == "bootstrap":
            self.loaded = True
        if args[0] == "bootout":
            was, self.loaded = self.loaded, False
            return (0 if was else 3), "", ""
        return 0, "", ""


def plist_for(tmp_path: Path) -> dict:
    return build_plist(label="com.careeros.tick", python="/opt/venv/bin/python", root=tmp_path / "repo",
                       runs_dir=tmp_path / "repo" / "data" / "runs", tick_minutes=15,
                       path_dirs=["/opt/claude/bin", "/opt/venv/bin"])


def test_plist_uses_absolute_paths_workdir_logs_and_path(tmp_path):
    p = plist_for(tmp_path)
    root = str(tmp_path / "repo")
    assert p["Label"] == "com.careeros.tick"
    assert p["ProgramArguments"] == ["/opt/venv/bin/python", "-m", "careeros.cli", "--root", root, "tick"]
    assert p["WorkingDirectory"] == root
    assert p["StartInterval"] == 900 and p["RunAtLoad"] is True
    assert p["StandardOutPath"].startswith(root) and p["StandardOutPath"].endswith("launchd.out.log")
    assert p["StandardErrorPath"].endswith("launchd.err.log")
    assert p["EnvironmentVariables"]["PATH"].startswith("/opt/claude/bin:/opt/venv/bin:")
    assert "/usr/bin" in p["EnvironmentVariables"]["PATH"]
    assert p["EnvironmentVariables"]["CAREEROS_ROOT"] == root
    assert all(Path(a).is_absolute() for a in (p["ProgramArguments"][0], p["WorkingDirectory"]))


def test_install_writes_plist_and_bootstraps(tmp_path):
    lc = FakeLaunchctl()
    agents = tmp_path / "LaunchAgents"
    out = install(plist_for(tmp_path), agents_dir=agents, launchctl=lc, uid=501)
    path = agents / "com.careeros.tick.plist"
    assert out["plist"] == str(path)
    assert plistlib.loads(path.read_bytes())["Label"] == "com.careeros.tick"
    assert ["bootstrap", "gui/501", str(path)] in lc.calls
    assert lc.calls.index(["bootout", "gui/501/com.careeros.tick"]) < lc.calls.index(["bootstrap", "gui/501", str(path)])
    assert (tmp_path / "repo" / "data" / "runs").is_dir()  # log dir exists before launchd writes to it


def test_install_reports_a_bootstrap_failure(tmp_path):
    def lc(args):
        return (5, "", "Bootstrap failed: 5: Input/output error") if args[0] == "bootstrap" else (0, "", "")
    with pytest.raises(RuntimeError, match="Bootstrap failed"):
        install(plist_for(tmp_path), agents_dir=tmp_path / "LA", launchctl=lc, uid=501)


def test_status_and_uninstall(tmp_path):
    lc = FakeLaunchctl()
    agents = tmp_path / "LaunchAgents"
    assert status("com.careeros.tick", agents_dir=agents, launchctl=lc, uid=501) == {
        "label": "com.careeros.tick", "installed": False, "loaded": False, "plist": str(agents / "com.careeros.tick.plist")}
    install(plist_for(tmp_path), agents_dir=agents, launchctl=lc, uid=501)
    st = status("com.careeros.tick", agents_dir=agents, launchctl=lc, uid=501)
    assert st["installed"] and st["loaded"]
    out = uninstall("com.careeros.tick", agents_dir=agents, launchctl=lc, uid=501)
    assert out["removed"] and not (agents / "com.careeros.tick.plist").exists()
    assert ["bootout", "gui/501/com.careeros.tick"] in lc.calls
    assert uninstall("com.careeros.tick", agents_dir=agents, launchctl=lc, uid=501)["removed"] is False
