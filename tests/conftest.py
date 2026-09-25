from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from careeros.config import Settings

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
# The shipped example candidate ("Alex Example"): examples/config + examples/profile. Tests use it
# directly and never read the personal, gitignored config/ and profile/ (CI has neither).
EXAMPLE_REPO = ROOT / "examples"

# Fictional boards served by the recorded HTTP fixtures (tests/fixtures/{greenhouse,lever,ashby}.json).
TEST_BOARDS = [
    {"company": "Acme", "ats": "greenhouse", "slug": "acme"},
    {"company": "Lever Co", "ats": "lever", "slug": "leverco"},
    {"company": "Ashby Co", "ats": "ashby", "slug": "ashbyco"},
    {"company": "Custom Co", "ats": "custom", "url": "https://careers.example.com"},
]


@pytest.fixture
def example_settings() -> Settings:
    return Settings.load(EXAMPLE_REPO)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings.load(EXAMPLE_REPO)
    s.paths["jobs_dir"] = tmp_path / "data" / "jobs"
    s.paths["seen_file"] = tmp_path / "data" / "seen.json"
    s.paths["tracker_xlsx"] = tmp_path / "JobTracker.xlsx"
    return s


def make_temp_root(dest: Path) -> Path:
    """A temp repo root: examples/{config,profile} copied to config/ + profile/, tracker and data paths
    kept inside the root, recorded-fixture boards, and templates/ when the checkout has them."""
    import yaml

    dest.mkdir(parents=True)
    shutil.copytree(EXAMPLE_REPO / "config", dest / "config")
    shutil.copytree(EXAMPLE_REPO / "profile", dest / "profile")
    companies = yaml.safe_load((dest / "config" / "companies.yaml").read_text())
    companies["boards"] = [dict(b) for b in TEST_BOARDS]
    (dest / "config" / "companies.yaml").write_text(yaml.safe_dump(companies, sort_keys=False))
    pipeline = yaml.safe_load((dest / "config" / "pipeline.yaml").read_text())
    pipeline["paths"]["tracker_xlsx"] = "JobTracker.xlsx"
    (dest / "config" / "pipeline.yaml").write_text(yaml.safe_dump(pipeline, sort_keys=False))
    if (ROOT / "templates").is_dir():
        shutil.copytree(ROOT / "templates", dest / "templates")
    return dest


@pytest.fixture
def temp_root(tmp_path: Path) -> Path:
    return make_temp_root(tmp_path / "repo")


def tectonic_cache() -> Path | None:
    """Tectonic's local bundle cache (a tool cache, not personal data), or None. PDF tests run only when it
    exists: with CAREEROS_LATEX_OFFLINE=1 tectonic reads this cache and never downloads (no network)."""
    env = os.environ.get("TECTONIC_CACHE_DIR")
    for cand in ([Path(env)] if env else []) + [Path.home() / "Library" / "Caches" / "TectonicProject.Tectonic",
                                                 Path.home() / ".cache" / "Tectonic"]:
        if cand.is_dir() and any(cand.iterdir()):
            return cand
    return None


def subprocess_env(root: Path, home: Path) -> dict[str, str]:
    """Env for `python -m careeros...` subprocesses: temp repo root, temp HOME, src on path, LaTeX offline."""
    env = dict(os.environ)
    env["CAREEROS_ROOT"] = str(root)
    env["HOME"] = str(home)
    env["CAREEROS_LATEX_OFFLINE"] = "1"
    cache = tectonic_cache()
    if cache:
        env["TECTONIC_CACHE_DIR"] = str(cache)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    return env


PY = sys.executable


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def load_script(relpath: str, name: str | None = None):
    """Import a standalone script (e.g. templates/resume/render.py) as a module."""
    import importlib.util

    path = ROOT / relpath
    mod_name = name or "_script_" + relpath.replace("/", "_").removesuffix(".py")
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _mon(v) -> str:
    s = str(v)
    if s == "present":
        return "Present"
    y, _, m = s.partition("-")
    return f"{_MONTHS[int(m) - 1]} {y}" if m else y


def build_resume_json(profile: dict, bullet_ids: list[str], job_id: str = "job000000001",
                      category: str = "swe_backend") -> dict:
    """resume.json (templates/resume/resume_schema.md) built only from `profile` bullets by id."""
    want = set(bullet_ids)

    def pick(entry):
        return [{"id": b["id"], "text": b["text"]} for b in entry.get("bullets") or [] if b["id"] in want]

    exp = [{"id": e["id"], "company": e["company"], "title": e.get("title_display") or e["title"],
            "location": e.get("location", ""), "start": _mon(e["start"]), "end": _mon(e["end"]), "bullets": pick(e)}
           for e in profile["experience"] if pick(e)]
    proj = [{"id": p["id"], "name": p["name"], "date": _mon(p["date"]), "stack": p.get("stack", [])[:3],
             "link": p.get("link"), "bullets": pick(p)} for p in profile.get("projects") or [] if pick(p)]
    edu = [{"id": e["id"], "school": e["school"], "degree": e["degree"], "gpa": e.get("gpa"),
            "start": _mon(e["start"]), "end": _mon(e["end"]), "coursework": e.get("coursework", [])}
           for e in profile["education"]]
    ident = {k: profile["identity"].get(k) for k in ("name", "email", "phone", "location", "linkedin", "github", "website")}
    return {
        "identity": ident,
        "summary": None,
        "sections": [{"type": t, "order": i} for i, t in enumerate(["experience", "projects", "education", "skills"], 1)],
        "experience": exp, "projects": proj, "education": edu,
        "skills": {k: list(v) for k, v in profile["skills"].items()},
        "meta": {"job_id": job_id, "category": category, "resume_version": f"{category}-v1", "template": "default"},
    }
