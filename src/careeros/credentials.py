"""Secret store for ATS / job-site logins used by /apply-job. Kept out of git and out of profile/.

File: `paths.credentials` in config/pipeline.yaml (default `~/.careeros/credentials.yaml`), mode 0600 in a 0700
directory. Shape: `{site: {username, password | secret_ref, notes}}`. Site names are lower-cased.

Backends (`credentials.backend` in config/pipeline.yaml):
- `file` (default): the password sits in the YAML file.
- `keychain` (macOS): the password goes to the login keychain (`security`, service `careeros:<site>`); the file keeps
  only `username`, `notes` and `secret_ref: keychain:careeros:<site>`. One item per site (account = site); the
  password reaches `security -i` hex-encoded on stdin, never on argv.

`redactor(settings)` masks every stored password (file and keychain, 4+ chars; also as JSON-escaped) in text:
headless run logs pass through it. `set_credential` refuses passwords shorter than 8 chars.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

import yaml

DEFAULT_PATH = "~/.careeros/credentials.yaml"
BACKENDS = ("file", "keychain")
MASK = "********"
MIN_REDACT_LEN = 4
MIN_PASSWORD_LEN = 8
SITE_RE = re.compile(r"[a-z0-9][a-z0-9._-]*")
KEYCHAIN_PREFIX = "keychain:"
Runner = Callable[..., subprocess.CompletedProcess]


def _run(argv: list[str], input: str | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, input=input, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        raise RuntimeError(f"keychain: could not run {argv[0]} ({e}); the keychain backend needs macOS") from e


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
    if not SITE_RE.fullmatch(k):
        raise ValueError(f"site must be a name of letters, digits, '.', '_' or '-', got {site!r}")
    return k


def _load(p: Path) -> dict[str, dict[str, Any]]:
    if not p.is_file():
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"{p}: not valid YAML ({e})") from e
    if not isinstance(data, dict):
        raise ValueError(f"{p}: must be a mapping of site -> {{username, password, notes}}")
    return {str(k).lower(): (v if isinstance(v, dict) else {}) for k, v in data.items()}


def _save(p: Path, data: dict[str, dict[str, Any]]) -> None:
    if not p.parent.is_dir():  # only a directory we create gets 0700; never chmod an existing one ($HOME, repo)
        p.parent.mkdir(parents=True, mode=0o700)
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
        if len(password) < MIN_PASSWORD_LEN:
            raise ValueError(f"password must be at least {MIN_PASSWORD_LEN} characters (shorter ones cannot be "
                             "masked safely in run logs)")
        if backend == "keychain":
            r = runner(["security", "-i"], input=f"add-generic-password -U -a {key} -s {_service(key)} "
                                                 f"-X {password.encode('utf-8').hex()}\n")
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
        r = runner(["security", "find-generic-password", "-a", key, "-s", ref[len(KEYCHAIN_PREFIX):], "-w"])
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
        r = runner(["security", "delete-generic-password", "-a", key, "-s", ref[len(KEYCHAIN_PREFIX):]])
        if r.returncode not in (0, 44):  # 44 = errSecItemNotFound: already gone
            raise RuntimeError(f"keychain: could not delete the password for {key}: {r.stderr.strip()}")
    _save(p, data)
    return True


def _stored_passwords(s: Any, runner: Runner) -> set[str]:
    """Every stored password: file ones, plus keychain ones that resolve (a keychain error skips that site)."""
    out: set[str] = set()
    for k, e in _load(credentials_path(s)).items():
        if e.get("password") is not None:
            out.add(str(e["password"]))
        elif str(e.get("secret_ref") or "").startswith(KEYCHAIN_PREFIX):
            try:
                pw = get_credential(s, k, runner=runner)["password"]
            except (KeyError, RuntimeError, OSError, ValueError):
                continue
            if pw:
                out.add(pw)
    return out


def redactor(s: Any, runner: Runner = _run) -> Callable[[str], str]:
    """A function masking every stored password (longest first) in a string, raw and JSON-escaped. Secrets are read
    once, when the redactor is built: a `creds set` after that is not masked by it."""
    try:
        raw = {x for x in _stored_passwords(s, runner) if len(x) >= MIN_REDACT_LEN}
    except (OSError, ValueError):
        raw = set()
    variants = raw | {json.dumps(x)[1:-1] for x in raw} | {json.dumps(x, ensure_ascii=False)[1:-1] for x in raw}
    secrets = sorted(variants, key=len, reverse=True)

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
