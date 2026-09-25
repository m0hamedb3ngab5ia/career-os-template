"""Skill docs are code: every `careeros ...` subcommand, repo file path and targets.yaml key a SKILL.md
references must exist (a wrong instruction in a skill is a defect; see docs/CODE_REVIEW_PROMPT.md)."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pytest
import yaml
from conftest import EXAMPLE_REPO, ROOT

from careeros.cli import build_parser

pytestmark = pytest.mark.unit

SKILLS = sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))
DOCS = SKILLS + sorted((ROOT / ".claude" / "skills" / "_shared").glob("*.md")) + sorted(
    (ROOT / "src" / "careeros" / "apply").glob("*.md"))
CLI_RE = re.compile(r"careeros((?: [a-z][a-z-]*)+)")
PATH_RE = re.compile(r"(?<![\w/.])((?:profile|config|templates|src/careeros)/[\w/.-]+\.(?:ya?ml|md|py|tex))")
TARGETS_KEY_RE = re.compile(r"targets\.yaml: ?([a-z_]+(?:\.[a-z_]+)+)")


def _ids(paths):
    return [str(p.relative_to(ROOT)) for p in paths]


def _subparsers(p: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for a in p._actions:
        if isinstance(a, argparse._SubParsersAction):
            return dict(a.choices)
    return {}


def _check_cli(words: list[str]) -> str | None:
    parser = build_parser()
    for i, w in enumerate(words):
        subs = _subparsers(parser)
        if not subs:
            return None  # reached a leaf command; the rest are positional args
        if w not in subs:
            return f"`careeros {' '.join(words[:i + 1])}`: unknown subcommand {w!r} (have {sorted(subs)})"
        parser = subs[w]
    return None if not _subparsers(parser) else f"`careeros {' '.join(words)}` needs a subcommand"


def test_skills_found():
    assert len(SKILLS) >= 8


@pytest.mark.parametrize("doc", DOCS, ids=_ids(DOCS))
def test_cli_references_exist(doc: Path):
    problems = []
    for m in CLI_RE.finditer(doc.read_text(encoding="utf-8")):
        words = m.group(1).split()
        if words and words[0] in ("careeros",):
            continue
        err = _check_cli(words)
        if err:
            problems.append(err)
    assert not problems, problems


@pytest.mark.parametrize("doc", DOCS, ids=_ids(DOCS))
def test_file_references_exist(doc: Path):
    missing = []
    for m in PATH_RE.finditer(doc.read_text(encoding="utf-8")):
        rel = m.group(1).rstrip(".")
        if "<" in rel or "*" in rel:
            continue
        # profile/ and config/ are personal and gitignored: the shipped examples must have the file
        base = EXAMPLE_REPO if rel.split("/")[0] in ("profile", "config") else ROOT
        if not (base / rel).exists():
            missing.append(rel)
    assert not missing, missing


@pytest.mark.parametrize("doc", DOCS, ids=_ids(DOCS))
def test_targets_keys_exist(doc: Path):
    targets = yaml.safe_load((EXAMPLE_REPO / "config" / "targets.yaml").read_text())
    missing = []
    for m in TARGETS_KEY_RE.finditer(doc.read_text(encoding="utf-8")):
        node = targets
        for part in m.group(1).split("."):
            if not isinstance(node, dict) or part not in node:
                missing.append(m.group(1))
                break
            node = node[part]
    assert not missing, missing


@pytest.mark.parametrize("skill", SKILLS, ids=_ids(SKILLS))
def test_frontmatter_name_matches_dir(skill: Path):
    text = skill.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    # Claude Code reads frontmatter line by line (descriptions may contain ": "), so do the same
    head = text.split("---", 2)[1]
    meta = dict(line.split(": ", 1) for line in head.strip().splitlines() if ": " in line)
    assert meta["name"] == skill.parent.name and meta.get("description")


def test_checker_catches_bad_references():
    assert _check_cli(["tracker", "applied-count"]) is None
    assert _check_cli(["tracker", "upsert"]) is None
    assert _check_cli(["job", "status"]) is None
    assert "unknown subcommand 'nope'" in _check_cli(["tracker", "nope"])
    assert "needs a subcommand" in _check_cli(["tracker"])


# --- prepare-job / write-cover-letter contracts ---------------------------------------------------

SKILL_DIR = ROOT / ".claude" / "skills"


def _skill(name: str) -> str:
    return (SKILL_DIR / name / "SKILL.md").read_text(encoding="utf-8")


COVER_RENDER_RE = re.compile(r"\.venv/bin/python templates/cover_letter/render\.py JOB/cover_letter\.md")


def test_prepare_job_renders_cover_letter_txt():
    """apply-job pastes cover_letter.txt; prepare-job must produce it (render.py) and list it."""
    text = _skill("prepare-job")
    assert COVER_RENDER_RE.search(text), "prepare-job must run templates/cover_letter/render.py JOB/cover_letter.md"
    files = re.search(r'"files": \[([^\]]*)\]', text).group(1)
    assert '"cover_letter.txt"' in files and '"resume.pdf"' in files


def _required_letter_regex() -> re.Pattern[str]:
    m = re.search(r"\(regex `([^`]+)`\)", _skill("prepare-job"))
    assert m, "prepare-job must state the cover-letter-required regex"
    return re.compile(m.group(1), re.I)


@pytest.mark.parametrize("posting,required", [
    ("Please submit a cover letter with your application.", True),
    ("A cover letter is required.", True),
    ("Cover letter required.", True),
    ("Please include a short cover letter.", True),
    ("Cover letters are optional.", False),
    ("We build ledgers.", False),
])
def test_cover_letter_required_regex_both_word_orders(posting, required):
    assert bool(_required_letter_regex().search(posting)) is required


def test_write_cover_letter_reads_length_and_voice_from_candidate_files():
    text = _skill("write-cover-letter")
    assert not re.search(r"\b120\s*[-–]\s*250\b", text), "length must come from config/qa.yaml, not a hardcode"
    assert "cover_letter.min_words" in text and "cover_letter.max_words" in text
    assert "close_variant" in text and "Dear Hiring Manager" in text
    assert "Hi <Company> team," not in text, "greeting format comes from the style guide"


def test_example_style_guide_declares_letter_settings():
    guide = (EXAMPLE_REPO / "profile" / "voice" / "style_guide.md").read_text(encoding="utf-8")
    for label in ("Greeting:", "Sign-off:", "Length:", "Close variants:"):
        assert re.search(rf"^- {re.escape(label)}", guide, re.M), label
    variants = re.search(r"^- Close variants:\n((?:  - .+\n)+)", guide, re.M)
    assert variants and len(variants.group(1).strip().splitlines()) >= 3


def test_tailor_resume_section_order_comes_from_config():
    text = _skill("tailor-resume")
    assert "resume.hard.section_order" in text
    assert "put `projects`\n   before `experience`" not in text and "projects` before `experience`" not in text


def test_tailor_resume_bullet_rule_matches_qa_fidelity():
    """QA bullet_fidelity accepts master text or a declared variant, optionally trimmed at the end; the
    skill must not promise more (e.g. free synonym swaps of the leading verb)."""
    rule = _skill("tailor-resume").split("1. Every bullet you output", 1)[1].split("\n2. ", 1)[0]
    assert "synonym" not in rule and "variants" in rule and "trailing" in rule
