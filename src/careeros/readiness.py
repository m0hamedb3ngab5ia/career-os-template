"""Readiness checklist (REQ-102) and the apply gate (REQ-103, DEC-004).

    items(root)          -> [{id, label, must, done, fix_link}]   (`careeros doctor`, GET /api/readiness)
    require_ready(root)  -> raises NotReady while any must-have is open (CLI exit 7, API 409)

Must-haves: a master résumé (profile/resumes/<rid>/meta.json type master), doctor clean (no example data, YAML
and schema ok), work-auth + sponsorship answers and the salary dropdown floor, `claude` installed, master.yaml
synced (no pending profile/master.proposed.yaml). Nice: a writing sample, ATS credentials, EEO answers.
Gates apply only; score/prepare never call it.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable

import yaml

NOT_READY_EXIT = 7
LEGAL_KEYS = ("work_authorization", "sponsorship")


class NotReady(Exception):
    def __init__(self, items: list[dict[str, Any]]):
        self.items = items
        super().__init__("not ready: " + ", ".join(i["id"] for i in items))


def _yaml(p: Path) -> dict:
    try:
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return d if isinstance(d, dict) else {}


def _has_master(root: Path) -> bool:
    for meta in (root / "profile" / "resumes").glob("*/meta.json"):
        try:
            if json.loads(meta.read_text(encoding="utf-8")).get("type") == "master":
                return True
        except (OSError, ValueError, AttributeError):
            continue
    return False


def items(root: Path, which: Callable[[str], str | None] = shutil.which,
          env: dict[str, str] | None = None) -> list[dict[str, Any]]:
    from careeros.doctor import FAIL, run_doctor

    root = Path(root)
    fails = {c.name for c in run_doctor(root, which=which, env=env) if c.level == FAIL}
    answers = _yaml(root / "profile" / "standard_answers.yaml")
    by_key = {a.get("key"): a.get("answer") for a in answers.get("answers") or [] if isinstance(a, dict)}
    candidate = _yaml(root / "config" / "targets.yaml").get("candidate") or {}
    pipeline = _yaml(root / "config" / "pipeline.yaml")
    cred = Path(str((pipeline.get("paths") or {}).get("credentials") or "~/.careeros/credentials.yaml")).expanduser()
    cred = cred if cred.is_absolute() else root / cred
    samples = root / "profile" / "voice" / "samples"
    rows = [
        ("master_resume", "Master résumé set", True, _has_master(root), "/profile#resumes"),
        ("setup_clean", "Profile has no example data (`careeros doctor` shows no FAIL)", True,
         not (fails - {"claude"}), "/profile"),
        ("legal_answers", "Work authorization + sponsorship answers set", True,
         all(by_key.get(k) not in (None, "") for k in LEGAL_KEYS), "/profile#answers"),
        ("salary_answer", "Salary floor set (config/targets.yaml candidate.salary_dropdown_floor_usd)", True,
         isinstance(candidate, dict) and candidate.get("salary_dropdown_floor_usd") not in (None, ""),
         "/settings"),
        ("claude", "Claude Code (`claude`) installed", True, "claude" not in fails, "/profile#readiness"),
        ("master_synced", "master.yaml synced with the master résumé", True,
         not (root / "profile" / "master.proposed.yaml").exists(), "/profile#resumes"),
        ("writing_sample", "At least one writing sample", False,
         samples.is_dir() and any(p.is_file() and not p.name.startswith(".") for p in samples.iterdir()),
         "/profile#samples"),
        ("credentials", "ATS logins saved (`careeros creds set`)", False, cred.is_file(), "/settings"),
        ("eeo_answers", "EEO answers set", False, bool(answers.get("eeo")), "/profile#answers"),
    ]
    return [{"id": i, "label": lbl, "must": m, "done": bool(d), "fix_link": link} for i, lbl, m, d, link in rows]


def status(root: Path) -> dict[str, Any]:
    """GET /api/readiness body."""
    its = items(root)
    return {"ready": all(i["done"] for i in its if i["must"]), "items": its}


def require_ready(root: Path) -> None:
    """Raise NotReady listing the open must-haves (every apply path calls this first)."""
    if os.environ.get("CAREEROS_TEST_SKIP_READINESS") == "1":  # tests/conftest.py only: suites predating the gate
        return
    if open_ := [i for i in items(root) if i["must"] and not i["done"]]:
        raise NotReady(open_)
