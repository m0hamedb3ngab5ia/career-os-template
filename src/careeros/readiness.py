"""Readiness checklist (REQ-102) and the apply gate (REQ-103, DEC-004).

    items(root)          -> [{id, label, must, done, fix_link}]   (`careeros doctor`, GET /api/readiness)
    require_ready(root)  -> raises NotReady while any must-have is open (CLI exit 7, API 409)

Must-haves: a master résumé (profile/resumes/<rid>/meta.json type master), doctor clean (no example data, YAML
and schema ok), work-auth + sponsorship answers and the salary dropdown floor, `claude` installed, master.yaml
synced (no pending or rejected master.yaml proposal, REQ-099). Nice: a writing sample, ATS credentials, EEO answers.
Gates apply only; score/prepare never call it.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable

import yaml

NOT_READY_EXIT = 7
LEGAL_KEYS = ("work_authorization", "sponsorship")
LEGAL_HINTS = ("legally authorized to work", "visa sponsorship")  # the examples' INSERT comments on those answers


class NotReady(Exception):
    def __init__(self, items: list[dict[str, Any]]):
        self.items = items
        super().__init__("not ready: " + ", ".join(i["label"] for i in items))


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


def _unchanged(root: Path, examples: Path | None, rel: str, hint: str) -> bool:
    """The example's `# INSERT` line holding `hint` is still verbatim in the candidate's file: an example value
    left unreviewed (a reviewed "Yes"/"No" equal to the example's is fine once its marker comment is gone)."""
    from careeros.doctor import MARKER_RE

    if examples is None:
        return False
    try:
        ex = (examples / rel).read_text(encoding="utf-8").splitlines()
        mine = {ln.strip() for ln in (root / rel).read_text(encoding="utf-8").splitlines()}
    except OSError:
        return False
    return any(ln.strip() in mine for ln in ex if hint in ln and MARKER_RE.search(ln))


def items(root: Path, which: Callable[[str], str | None] | None = None,
          env: dict[str, str] | None = None, checks: list | None = None) -> list[dict[str, Any]]:
    """`checks`: a run_doctor result already in hand (`careeros doctor`), else run here."""
    from careeros import master_sync
    from careeros.doctor import FAIL, find_examples, run_doctor

    root = Path(root)
    examples = find_examples(root)
    if checks is None:
        checks = run_doctor(root, which=which or shutil.which, examples=examples, env=env)
    fails = {c.name for c in checks if c.level == FAIL}
    answers = _yaml(root / "profile" / "standard_answers.yaml")
    by_key = {a.get("key"): a.get("answer") for a in answers.get("answers") or [] if isinstance(a, dict)}
    candidate = _yaml(root / "config" / "targets.yaml").get("candidate") or {}
    paths = _yaml(root / "config" / "pipeline.yaml").get("paths")
    cred = Path(str((paths if isinstance(paths, dict) else {}).get("credentials")
                    or "~/.careeros/credentials.yaml")).expanduser()
    cred = cred if cred.is_absolute() else root / cred
    samples = root / "profile" / "voice" / "samples"
    rows = [
        ("master_resume", "Master résumé set", True, _has_master(root), "/profile#resumes"),
        ("setup_clean", "Profile has no example data (`careeros doctor` shows no FAIL)", True,
         not (fails - {"claude"}), "/profile"),
        ("legal_answers", "Work authorization + sponsorship answers set", True,
         all(by_key.get(k) not in (None, "") for k in LEGAL_KEYS)
         and not any(_unchanged(root, examples, "profile/standard_answers.yaml", h) for h in LEGAL_HINTS),
         "/profile#answers"),
        ("salary_answer", "Salary floor set (config/targets.yaml candidate.salary_dropdown_floor_usd)", True,
         isinstance(candidate, dict) and candidate.get("salary_dropdown_floor_usd") not in (None, "")
         and not _unchanged(root, examples, "config/targets.yaml", "salary_dropdown_floor_usd:"),
         "/settings"),
        ("claude", "Claude Code (`claude`) installed", True, "claude" not in fails, "/profile#readiness"),
        ("master_synced", "master.yaml synced with the master résumé", True,
         master_sync.state(root)["state"] == "synced", "/profile#resumes"),
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
    if open_ := [i for i in items(root) if i["must"] and not i["done"]]:
        raise NotReady(open_)
