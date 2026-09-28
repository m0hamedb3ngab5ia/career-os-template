"""careeros.credentials: the secret store for ATS / job-site logins (file or macOS keychain backend), redaction,
and the doctor check. Everything lives under tmp_path; never $HOME."""
from __future__ import annotations

import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from careeros import credentials as cr
from careeros.doctor import PASS, WARN, check_credentials

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def s(settings, tmp_path: Path):
    settings.paths["credentials"] = tmp_path / "secrets" / "credentials.yaml"
    settings.pipeline = dict(settings.pipeline, credentials={"backend": "file"})
    return settings


def _mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


def test_file_roundtrip_mode_0600_and_list_has_no_secrets(s):
    cr.set_credential(s, "workday", username="cand@example.com", password="hunter2-pw", notes="tenant acme")
    p = s.paths["credentials"]
    assert _mode(p) == 0o600 and _mode(p.parent) == 0o700
    assert yaml.safe_load(p.read_text())["workday"] == {"username": "cand@example.com", "password": "hunter2-pw",
                                                          "notes": "tenant acme"}
    got = cr.get_credential(s, "Workday")          # site names are case-insensitive
    assert got["password"] == "hunter2-pw" and got["username"] == "cand@example.com"
    listed = cr.list_credentials(s)
    assert listed == [{"site": "workday", "username": "cand@example.com", "notes": "tenant acme",
                       "has_secret": True, "backend": "file"}]
    assert "hunter2-pw" not in repr(listed)
    cr.set_credential(s, "workday", username="other@example.com")      # keeps the stored password
    assert cr.get_credential(s, "workday")["password"] == "hunter2-pw"
    assert cr.remove_credential(s, "workday") is True
    assert cr.remove_credential(s, "workday") is False
    assert cr.list_credentials(s) == [] and _mode(p) == 0o600
    with pytest.raises(KeyError):
        cr.get_credential(s, "workday")


def test_default_path_is_under_home_careeros(s, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    del s.paths["credentials"]
    assert cr.credentials_path(s) == tmp_path / "home" / ".careeros" / "credentials.yaml"


def test_example_config_ships_the_default_path():
    pipe = yaml.safe_load((ROOT / "examples" / "config" / "pipeline.yaml").read_text())
    assert pipe["paths"]["credentials"] == "~/.careeros/credentials.yaml"
    assert pipe["credentials"]["backend"] == "file"
    text = (ROOT / "examples" / "config" / "pipeline.yaml").read_text()
    assert any("credentials" in ln and "(Recommended)" in ln for ln in text.splitlines())
    assert "credentials.yaml" in (ROOT / ".gitignore").read_text()


def test_bad_site_and_backend_rejected(s):
    with pytest.raises(ValueError):
        cr.set_credential(s, "  ", username="u", password="p")
    s.pipeline["credentials"] = {"backend": "vault"}
    with pytest.raises(ValueError):
        cr.backend_name(s)


class FakeSecurity:
    def __init__(self):
        self.store: dict[tuple[str, str], str] = {}
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], input: str | None = None) -> subprocess.CompletedProcess:
        self.calls.append(argv)
        a = dict(zip(argv[2::2], argv[3::2])) if argv[1] != "add-generic-password" else {}
        if argv[1] == "add-generic-password":
            args = argv[2:]
            opts = {args[i]: args[i + 1] for i in range(len(args) - 1) if args[i] in ("-a", "-s", "-w")}
            self.store[(opts["-s"], opts["-a"])] = opts["-w"]
            return subprocess.CompletedProcess(argv, 0, "", "")
        if argv[1] == "find-generic-password":
            for (svc, _acct), pw in self.store.items():
                if svc == a.get("-s"):
                    return subprocess.CompletedProcess(argv, 0, pw + "\n", "")
            return subprocess.CompletedProcess(argv, 44, "", "not found")
        if argv[1] == "delete-generic-password":
            self.store = {k: v for k, v in self.store.items() if k[0] != a.get("-s")}
            return subprocess.CompletedProcess(argv, 0, "", "")
        raise AssertionError(argv)


def test_keychain_backend_keeps_the_secret_out_of_the_file(s):
    s.pipeline["credentials"] = {"backend": "keychain"}
    sec = FakeSecurity()
    cr.set_credential(s, "greenhouse", username="u@example.com", password="kc-secret-9", runner=sec)
    doc = yaml.safe_load(s.paths["credentials"].read_text())
    assert doc["greenhouse"] == {"username": "u@example.com", "secret_ref": "keychain:careeros:greenhouse"}
    assert "kc-secret-9" not in s.paths["credentials"].read_text()
    assert cr.get_credential(s, "greenhouse", runner=sec)["password"] == "kc-secret-9"
    assert cr.list_credentials(s)[0]["has_secret"] is True
    assert cr.remove_credential(s, "greenhouse", runner=sec) is True
    assert sec.store == {}


def test_redact_masks_every_stored_password(s):
    cr.set_credential(s, "lever", username="u", password="s3cr3t-value")
    cr.set_credential(s, "tiny", username="u", password="abc")      # too short to mask safely: skipped
    red = cr.redactor(s)
    assert red('{"text": "typed s3cr3t-value into the box"}') == '{"text": "typed ******** into the box"}'
    assert red("abc stays") == "abc stays"
    assert cr.redactor_for_root(Path("/nonexistent-root"))("x s3cr3t-value") == "x s3cr3t-value"  # no setup: no-op


def test_headless_invoke_redacts_the_stream_log_and_result(tmp_path):
    from conftest import make_temp_root

    from careeros.runs.headless import invoke

    root = make_temp_root(tmp_path / "repo")
    pipe_p = root / "config" / "pipeline.yaml"
    pipe = yaml.safe_load(pipe_p.read_text())
    pipe["paths"]["credentials"] = str(tmp_path / "c" / "credentials.yaml")
    pipe_p.write_text(yaml.safe_dump(pipe))
    from careeros.config import Settings

    cr.set_credential(Settings.load(root), "workday", username="u", password="leaky-pass-42")
    line = '{"type":"result","subtype":"success","is_error":false,"result":"logged in with leaky-pass-42"}'
    stream = tmp_path / "out.stream.jsonl"
    res = invoke([sys.executable, "-c", f"print({line!r})"], str(root), {"PATH": "/usr/bin:/bin"}, 30, stream)
    assert "leaky-pass-42" not in stream.read_text() and "********" in stream.read_text()
    assert "leaky-pass-42" not in repr(res.summary())


def test_doctor_credentials_check(tmp_path):
    p = tmp_path / "home" / ".careeros" / "credentials.yaml"
    assert check_credentials(p)[0].level == PASS                      # absent: nothing to check
    p.parent.mkdir(parents=True)
    p.write_text("x: {username: u, password: p}\n")
    p.chmod(0o644)
    got = check_credentials(p)
    assert [c.level for c in got] == [WARN] and "0600" in got[0].detail
    p.chmod(0o600)
    assert [c.level for c in check_credentials(p)] == [PASS]
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    inside = repo / "sub" / "credentials.yaml"
    inside.write_text("{}\n")
    inside.chmod(0o600)
    got = check_credentials(inside)
    assert got[0].level == WARN and "not gitignored" in got[0].detail
    (repo / ".gitignore").write_text("credentials.yaml\n")
    got = check_credentials(inside)
    assert got[0].level == WARN and "inside the git repo" in got[0].detail and "not gitignored" not in got[0].detail
