"""The shipped example files are the new user's form: every personal line says what to insert, every file
explains itself, and reusable defaults are labeled as fine to keep."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from conftest import EXAMPLE_REPO

pytestmark = pytest.mark.unit

YAMLS = sorted((EXAMPLE_REPO / "profile").glob("*.yaml")) + sorted((EXAMPLE_REPO / "config").glob("*.yaml"))
IDS = [str(p.relative_to(EXAMPLE_REPO)) for p in YAMLS]
INSERT_RE = re.compile(r"#\s*INSERT:\s*(.*)$")
REUSABLE = "reusable default: fine to keep"


def lines(p: Path) -> list[str]:
    return p.read_text(encoding="utf-8").splitlines()


def insert_note(line: str) -> str | None:
    m = INSERT_RE.search(line)
    return m.group(1).strip() if m else None


@pytest.mark.parametrize("path", YAMLS, ids=IDS)
def test_header_block(path: Path):
    head = "\n".join(ln for ln in lines(path)[:40] if ln.startswith("#"))
    for part in ("What this file is", "What you must fill in", "What you can leave as is"):
        assert part in head, f"{path.name}: header missing {part!r}"


@pytest.mark.parametrize("path", YAMLS, ids=IDS)
def test_no_bare_edit_markers_and_inserts_are_explained(path: Path):
    for i, ln in enumerate(lines(path), 1):
        assert not re.search(r"#\s*EDIT\b", ln), f"{path.name}:{i} bare # EDIT left: {ln.strip()}"
        note = insert_note(ln)
        if note is not None:
            assert len(note) >= 8, f"{path.name}:{i} INSERT needs what/format/example: {ln.strip()}"


@pytest.mark.parametrize("path", YAMLS, ids=IDS)
def test_still_valid_yaml(path: Path):
    assert isinstance(yaml.safe_load(path.read_text(encoding="utf-8")), dict)


def _key_lines(path: Path, key_re: str) -> list[str]:
    return [ln for ln in lines(path) if re.match(key_re, ln)]


def test_identity_lines_are_insert_marked():
    got = _key_lines(EXAMPLE_REPO / "profile" / "master.yaml",
                     r"\s+(name|email|phone|location|linkedin|github|website|pronouns):")[:8]
    assert len(got) == 8
    assert all(insert_note(ln) for ln in got), [ln for ln in got if not insert_note(ln)]


# standard_answers keys whose answer is about the candidate (the rest are generic behavior defaults)
PERSONAL_ANSWERS = {
    "work_authorization", "sponsorship", "citizenship", "over_18", "relocate", "remote_hybrid", "start_date",
    "current_employer", "current_title", "years_experience_fulltime", "years_experience", "degree", "school",
    "major", "grad_year", "gpa", "non_compete", "security_clearance", "linkedin", "github", "pronouns", "phone",
    "address",
}


def test_personal_standard_answers_are_insert_marked():
    key = None
    missing = []
    for ln in lines(EXAMPLE_REPO / "profile" / "standard_answers.yaml"):
        m = re.match(r"\s*- key: (\w+)", ln)
        if m:
            key = m.group(1)
        elif re.match(r"\s+answer:", ln) and key in PERSONAL_ANSWERS and not insert_note(ln):
            missing.append(key)
    assert not missing, missing
    eeo = "\n".join(lines(EXAMPLE_REPO / "profile" / "standard_answers.yaml")).split("\neeo:")[1]
    assert all(insert_note(ln) for ln in eeo.splitlines() if re.match(r"\s+answer:", ln))


@pytest.mark.parametrize("rel,key_re", [
    ("config/targets.yaml", r"\s+(level|graduation|min_base_usd|salary_dropdown_floor_usd|work_authorization|needs_sponsorship|preferred):"),
    ("config/companies.yaml", r"(dream_list|already_applied):|\s+(companies|industries|name_patterns):"),
    ("config/categories.yaml", r"\s+bullet_priority:"),
    ("profile/confidential_terms.yaml", r"(employer|terms):"),
])
def test_personal_config_lines_are_insert_marked(rel: str, key_re: str):
    got = _key_lines(EXAMPLE_REPO / rel, key_re)
    assert got and all(insert_note(ln) for ln in got), [ln for ln in got if not insert_note(ln)]


@pytest.mark.parametrize("rel,sections", [
    ("config/qa.yaml", ["banned_phrases"]),
    ("config/pipeline.yaml", ["schedule"]),
    ("config/categories.yaml", ["swe_backend"]),
    ("config/companies.yaml", ["boards", "prestige_tiers"]),
    ("config/targets.yaml", ["thresholds", "tiers"]),
])
def test_reusable_defaults_are_labeled(rel: str, sections: list[str]):
    text = (EXAMPLE_REPO / rel).read_text(encoding="utf-8")
    assert REUSABLE in text, rel
    for sec in sections:
        i = text.index(f"\n{sec}:")
        window = text[max(0, i - 300): i + 200]
        assert REUSABLE in window, f"{rel}: {sec} not labeled {REUSABLE!r}"


def test_volume_documents_deadline_clusters_and_company_caps_example():
    targets = yaml.safe_load((EXAMPLE_REPO / "config" / "targets.yaml").read_text(encoding="utf-8"))
    assert targets["volume"]["deadline_cluster_days"] == 7
    assert targets["volume"]["max_per_company_per_90_days"] == 2
    assert targets["volume"]["same_company_cooldown_days"] == 30
    text = (EXAMPLE_REPO / "config" / "companies.yaml").read_text(encoding="utf-8")
    assert "# company_caps:" in text and "published limit" in text
    assert "company_caps" not in yaml.safe_load(text)  # an example only: off by default
