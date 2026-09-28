"""Secret store for ATS / job-site logins used by /apply-job. Kept out of git and out of profile/.

File: `paths.credentials` in config/pipeline.yaml (default `~/.careeros/credentials.yaml`), mode 0600 in a 0700
directory. Shape: `{site: {username, password | secret_ref, notes}}`. Site names are lower-cased.

Backends (`credentials.backend` in config/pipeline.yaml):
- `file` (default): the password sits in the YAML file.
- `keychain` (macOS): the password goes to the login keychain (`security`, service `careeros:<site>`); the file keeps
  only `username`, `notes` and `secret_ref: keychain:careeros:<site>`. Note: `security add-generic-password -w` puts
  the password on its argv for the moment the command runs.

`redactor(settings)` masks every stored file-backend password (4+ chars) in text: headless run logs pass through it.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

import yaml

DEFAULT_PATH = "~/.careeros/credentials.yaml"
BACKENDS = ("file", "keychain")
MASK = "********"
MIN_REDACT_LEN = 4
KEYCHAIN_PREFIX = "keychain:"
Runner = Callable[..., subprocess.CompletedProcess]


def _run(argv: list[str], input: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(argv, input=input, capture_output=True, text=True, timeout=30)


def credentials_path(s: Any) -> Path:
    p = s.paths.get("credentials")
    return Path(p) if p else Path(DEFAULT_PATH).expanduser()


def backend_name(s: Any) -> str:
    b = str(((s.pipeline.get("credentials") or {}).get("backend")) or "file").strip().lower()
    if b not in BACKENDS:
        raise ValueError(f"config/pipeline.yaml: credentials.backend must be one of {', '.join(BACKENDS)}, got {b!r}")
    return b


def _site(site: str) -> str:
    k = str(site or "").strip().lower()
    if not k or any(c.isspace() for c in k):
        raise ValueError(f"site must be a non-empty name without spaces, got {site!r}")
    return k


def _load(p: Path) -> dict[str, dict[str, Any]]:
    if not p.is_file():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{p}: must be a mapping of site -> {{username, password, notes}}")
    return {str(k).lower(): (v if isinstance(v, dict) else {}) for k, v in data.items()}


def _save(p: Path, data: dict[str, dict[str, Any]]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(p.parent, 0o700)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".credentials.", suffix=".tmp")  # mkstemp creates it 0600
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, sort_keys=True, allow_unicode=True)
        os.chmod(tmp, 0o600)
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _service(site: str) -> str:
    return f"careeros:{site}"


def set_credential(s: Any, site: str, *, username: str | None = None, password: str | None = None,
                   notes: str | None = None, runner: Runner = _run) -> dict[str, Any]:
    """Create or update one site. Omitted fields keep their stored value."""
    key, p, backend = _site(site), credentials_path(s), backend_name(s)
    data = _load(p)
    e = dict(data.get(key) or {})
    if username is not None:
        e["username"] = username
    if notes is not None:
        e["notes"] = notes
    if password is not None:
        if backend == "keychain":
            r = runner(["security", "add-generic-password", "-U", "-a", e.get("username") or key,
                        "-s", _service(key), "-w", password])
            if r.returncode != 0:
                raise RuntimeError(f"keychain: could not store the password for {key}: {r.stderr.strip()}")
            e.pop("password", None)
            e["secret_ref"] = KEYCHAIN_PREFIX + _service(key)
        else:
            e.pop("secret_ref", None)
            e["password"] = password
    data[key] = e
    _save(p, data)
    return {k: v for k, v in e.items() if k != "password"}


def get_credential(s: Any, site: str, runner: Runner = _run) -> dict[str, Any]:
    """{site, username, notes, password} (password None when none stored). KeyError if the site is unknown."""
    key = _site(site)
    e = _load(credentials_path(s)).get(key)
    if e is None:
        raise KeyError(key)
    pw = e.get("password")
    ref = str(e.get("secret_ref") or "")
    if pw is None and ref.startswith(KEYCHAIN_PREFIX):
        r = runner(["security", "find-generic-password", "-s", ref[len(KEYCHAIN_PREFIX):], "-w"])
        if r.returncode != 0:
            raise RuntimeError(f"keychain: no password for {key} ({ref})")
        pw = r.stdout.rstrip("\n")
    return {"site": key, "username": e.get("username"), "notes": e.get("notes"), "password": pw}


def list_credentials(s: Any) -> list[dict[str, Any]]:
    """Every site without its secret."""
    return [{"site": k, "username": e.get("username"), "notes": e.get("notes"),
             "has_secret": bool(e.get("password") or e.get("secret_ref")),
             "backend": "keychain" if str(e.get("secret_ref") or "").startswith(KEYCHAIN_PREFIX) else "file"}
            for k, e in sorted(_load(credentials_path(s)).items())]


def remove_credential(s: Any, site: str, runner: Runner = _run) -> bool:
    key, p = _site(site), credentials_path(s)
    data = _load(p)
    e = data.pop(key, None)
    if e is None:
        return False
    ref = str(e.get("secret_ref") or "")
    if ref.startswith(KEYCHAIN_PREFIX):
        runner(["security", "delete-generic-password", "-s", ref[len(KEYCHAIN_PREFIX):]])
    _save(p, data)
    return True


def redactor(s: Any) -> Callable[[str], str]:
    """A function masking every stored file-backend password (longest first) in a string."""
    try:
        secrets = sorted({str(e["password"]) for e in _load(credentials_path(s)).values()
                          if e.get("password") is not None and len(str(e["password"])) >= MIN_REDACT_LEN},
                         key=len, reverse=True)
    except (OSError, ValueError, yaml.YAMLError):
        secrets = []

    def red(text: str) -> str:
        for x in secrets:
            if x in text:
                text = text.replace(x, MASK)
        return text

    return red


def redactor_for_root(root: Path) -> Callable[[str], str]:
    """`redactor` for a repo root; a no-op when the root has no usable setup."""
    from careeros.config import ConfigError, Settings

    try:
        return redactor(Settings.load(Path(root)))
    except (ConfigError, FileNotFoundError, OSError, SystemExit, yaml.YAMLError):
        return lambda t: t
