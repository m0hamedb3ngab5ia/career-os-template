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
