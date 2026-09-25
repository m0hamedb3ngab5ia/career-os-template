"""Unit tests for careeros.doctor: the setup checklist (fresh example copy fails, filled-in root passes)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from conftest import EXAMPLE_REPO, personalize

from careeros.doctor import (
    FAIL,
    PASS,
    WARN,
    Check,
    exit_code,
    format_report,
    run_doctor,
    schema_problems,
)

pytestmark = pytest.mark.unit

ALL_TOOLS = {"claude", "tectonic", "pdflatex", "gh", "codex"}


def which_from(present: set[str]):
    return lambda name: f"/fake/bin/{name}" if name in present else None


def fresh(tmp_path: Path) -> Path:
    """What `careeros init` produces: examples/{config,profile} copied verbatim."""
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copytree(EXAMPLE_REPO / "config", root / "config")
    shutil.copytree(EXAMPLE_REPO / "profile", root / "profile")
    return root


def filled(tmp_path: Path) -> Path:
    return personalize(fresh(tmp_path))


def doctor(root: Path, tools: set[str] = ALL_TOOLS) -> list[Check]:
    return run_doctor(root, which=which_from(tools), examples=EXAMPLE_REPO)


def details(checks: list[Check], level: str) -> list[str]:
    return [f"{c.name}: {c.detail}" for c in checks if c.level == level]


def text_of(checks: list[Check], level: str) -> str:
    return "\n".join(details(checks, level))


# --- setup ------------------------------------------------------------------------------------

def test_missing_personal_dirs_fail(tmp_path: Path):
    checks = doctor(tmp_path)
    fails = text_of(checks, FAIL)
    assert "profile/" in fails and "config/" in fails and "careeros init" in fails
    assert exit_code(checks) == 1


def test_invalid_yaml_fails_with_file_name(tmp_path: Path):
    root = filled(tmp_path)
    (root / "config" / "targets.yaml").write_text("candidate: [unclosed\n")
    checks = doctor(root)
    assert "config/targets.yaml" in text_of(checks, FAIL)
    assert exit_code(checks) == 1


def test_missing_required_key_fails(tmp_path: Path):
    root = filled(tmp_path)
    t = yaml.safe_load((root / "config" / "targets.yaml").read_text())
    del t["tiers"]
    (root / "config" / "targets.yaml").write_text(yaml.safe_dump(t))
    assert "config/targets.yaml: tiers" in text_of(doctor(root), FAIL)


def test_schema_problems_empty_for_examples():
    load = lambda p: yaml.safe_load(p.read_text())  # noqa: E731
    cfg = {n: load(EXAMPLE_REPO / "config" / f"{n}.yaml") for n in ("targets", "categories", "companies", "qa", "pipeline")}
    prof = {n: load(EXAMPLE_REPO / "profile" / f"{n}.yaml") for n in ("master", "standard_answers", "confidential_terms")}
    assert schema_problems(cfg, prof) == []


def test_schema_problems_names_missing_standard_answer_key():
    load = lambda p: yaml.safe_load(p.read_text())  # noqa: E731
    cfg = {n: load(EXAMPLE_REPO / "config" / f"{n}.yaml") for n in ("targets", "categories", "companies", "qa", "pipeline")}
    prof = {n: load(EXAMPLE_REPO / "profile" / f"{n}.yaml") for n in ("master", "standard_answers", "confidential_terms")}
    prof["standard_answers"]["answers"] = [a for a in prof["standard_answers"]["answers"] if a["key"] != "phone"]
    probs = schema_problems(cfg, prof)
    assert any("profile/standard_answers.yaml" in p and "phone" in p for p in probs), probs


# --- untouched example data = FAIL ------------------------------------------------------------

def test_fresh_example_copy_fails_on_identity(tmp_path: Path):
    checks = doctor(fresh(tmp_path))
    fails = text_of(checks, FAIL)
    for key in ("identity.name", "identity.email", "identity.phone", "identity.linkedin", "identity.github"):
        assert f"profile/master.yaml: {key}" in fails, key
    assert "Alex Example" in fails
    assert exit_code(checks) == 1


def test_fresh_copy_fails_on_example_ids_and_standard_answers(tmp_path: Path):
    fails = text_of(doctor(fresh(tmp_path)), FAIL)
    assert "experience id 'acme'" in fails and "experience id 'initech_intern'" in fails
    assert "profile/standard_answers.yaml" in fails and "identical to the example" in fails


def test_example_dot_com_email_anywhere_fails(tmp_path: Path):
    root = filled(tmp_path)
    sa = yaml.safe_load((root / "profile" / "standard_answers.yaml").read_text())
    sa["answers"].append({"key": "email", "match": ["email"], "answer": "sam@example.com"})
    (root / "profile" / "standard_answers.yaml").write_text(yaml.safe_dump(sa))
    fails = text_of(doctor(root), FAIL)
    assert "profile/standard_answers.yaml" in fails and "sam@example.com" in fails


def test_single_example_identity_field_left_fails(tmp_path: Path):
    root = filled(tmp_path)
    m = yaml.safe_load((root / "profile" / "master.yaml").read_text())
    m["identity"]["github"] = "https://github.com/alex-example"
    (root / "profile" / "master.yaml").write_text(yaml.safe_dump(m))
    fails = details(doctor(root), FAIL)
    assert any("profile/master.yaml: identity.github" in f for f in fails), fails
    assert not any("identity.name" in f for f in fails)


def test_filled_in_root_passes(tmp_path: Path):
    checks = doctor(filled(tmp_path))
    assert details(checks, FAIL) == []
    assert exit_code(checks) == 0
    assert any(c.level == PASS and c.name == "example_data" for c in checks)


# --- INSERT / EDIT markers --------------------------------------------------------------------

def test_unchanged_insert_lines_warn_with_file_and_line(tmp_path: Path):
    root = filled(tmp_path)
    shutil.copy(EXAMPLE_REPO / "config" / "targets.yaml", root / "config" / "targets.yaml")
    warns = [d for d in details(doctor(root), WARN) if d.startswith("unchanged_placeholder")]
    assert warns and all("config/targets.yaml:" in w for w in warns), warns
    assert any("min_base_usd" in w for w in warns)


def test_edited_or_reviewed_insert_line_does_not_warn(tmp_path: Path):
    root = filled(tmp_path)
    src = (EXAMPLE_REPO / "config" / "targets.yaml").read_text()
    marked = [ln for ln in src.splitlines() if "# INSERT" in ln]
    # change every value (keep the comments) -> nothing unchanged
    out = src
    for ln in marked:
        out = out.replace(ln, ln.replace("# INSERT", "#changed INSERT", 1).replace(":", ": ", 1), 1)
    (root / "config" / "targets.yaml").write_text(out)
    assert not [d for d in details(doctor(root), WARN) if "config/targets.yaml" in d]


def test_legacy_edit_marker_also_warns(tmp_path: Path):
    root = filled(tmp_path)
    ex = tmp_path / "ex"
    shutil.copytree(EXAMPLE_REPO, ex)
    (ex / "config" / "targets.yaml").write_text((ex / "config" / "targets.yaml").read_text()
                                                + "legacy_key: 1   # EDIT\n")
    (root / "config" / "targets.yaml").write_text((root / "config" / "targets.yaml").read_text()
                                                  + "legacy_key: 1   # EDIT\n")
    checks = run_doctor(root, which=which_from(ALL_TOOLS), examples=ex)
    assert any("legacy_key" in d for d in details(checks, WARN))


# --- categories --------------------------------------------------------------------------------

def test_bullet_priority_unknown_id_fails(tmp_path: Path):
    root = filled(tmp_path)
    c = yaml.safe_load((root / "config" / "categories.yaml").read_text())
    c["swe_backend"]["bullet_priority"] = ["northwind", "ghost_job"]
    (root / "config" / "categories.yaml").write_text(yaml.safe_dump(c))
    fails = text_of(doctor(root), FAIL)
    assert "config/categories.yaml: swe_backend.bullet_priority" in fails and "ghost_job" in fails


def test_fresh_bullet_priority_matches_example_ids(tmp_path: Path):
    """On the untouched copy ids agree (acme is in both); the example_data check is what fails."""
    fails = text_of(doctor(fresh(tmp_path)), FAIL)
    assert "bullet_priority" not in fails


# --- tools ------------------------------------------------------------------------------------

def test_missing_claude_fails(tmp_path: Path):
    checks = doctor(filled(tmp_path), tools=ALL_TOOLS - {"claude"})
    assert "claude" in text_of(checks, FAIL)
    assert exit_code(checks) == 1


def test_missing_optional_tools_warn(tmp_path: Path):
    checks = doctor(filled(tmp_path), tools={"claude"})
    warns = text_of(checks, WARN)
    assert "tectonic" in warns and "pdflatex" in warns and "gh" in warns and "codex" in warns
    assert exit_code(checks) == 0


def test_pdflatex_alone_is_enough(tmp_path: Path):
    checks = doctor(filled(tmp_path), tools={"claude", "pdflatex", "gh", "codex"})
    assert not [c for c in checks if c.name == "latex" and c.level != PASS]


# --- voice ------------------------------------------------------------------------------------

def test_no_voice_samples_warns(tmp_path: Path):
    root = filled(tmp_path)
    for f in (root / "profile" / "voice" / "samples").iterdir():
        f.unlink()
    (root / "profile" / "voice" / "samples" / ".gitkeep").write_text("")
    assert "voice" in text_of(doctor(root), WARN)


def test_voice_sample_present_passes(tmp_path: Path):
    checks = doctor(filled(tmp_path))
    assert any(c.name == "voice_samples" and c.level == PASS for c in checks)


# --- report -----------------------------------------------------------------------------------

def test_format_report_full_and_quiet():
    checks = [Check(PASS, "setup", "ok"), Check(WARN, "voice_samples", "0 samples"), Check(FAIL, "example_data", "x")]
    full = format_report(checks)
    assert "PASS" in full and "WARN" in full and "FAIL" in full and "1 fail, 1 warn, 1 pass" in full
    quiet = format_report(checks, quiet=True)
    assert "FAIL" in quiet and "voice_samples" not in quiet and "setup" not in quiet
    assert format_report([Check(PASS, "setup", "ok")], quiet=True) == ""
    assert exit_code(checks) == 1 and exit_code(checks[:2]) == 0


def test_placeholder_warnings_are_one_line_per_file_with_line_and_key(tmp_path: Path):
    warns = [d for d in details(doctor(fresh(tmp_path)), WARN) if d.startswith("unchanged_placeholder")]
    files = [w.split(": ")[1] for w in warns]
    assert len(files) == len(set(files))  # grouped per file, not one line per placeholder
    sa = next(w for w in warns if "profile/standard_answers.yaml" in w)
    assert "phone.answer" in sa and "gender.answer" in sa  # repeated keys qualified by their entry
    assert any("config/targets.yaml" in w and "min_base_usd" in w for w in warns)
