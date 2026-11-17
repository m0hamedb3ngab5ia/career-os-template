"""docs/CATALOGUE.md must mention every skill and every top-level careeros subcommand."""
import argparse
import re
from pathlib import Path

from careeros import cli

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = (ROOT / "docs" / "CATALOGUE.md").read_text(encoding="utf-8")

# Skill dirs that are not user-facing skills (no entry needed).
SKILL_ALLOWLIST = {"_shared"}  # shared helper files, not a skill
# Subcommands that are internal (none today; add with a comment why).
COMMAND_ALLOWLIST: set[str] = set()


def _commands():
    for action in cli.build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return sorted(action.choices)
    return []


def test_every_skill_is_listed():
    skills = sorted(p.name for p in (ROOT / ".claude" / "skills").iterdir() if p.is_dir())
    missing = [s for s in skills if s not in SKILL_ALLOWLIST and f"/{s}" not in CATALOGUE]
    assert not missing, f"add to docs/CATALOGUE.md as `/name`: {missing}"


def test_every_command_is_listed():
    cmds = _commands()
    assert cmds, "no subcommands found"
    missing = [c for c in cmds if c not in COMMAND_ALLOWLIST
               and not re.search(rf"careeros {re.escape(c)}\b", CATALOGUE)]
    assert not missing, f"add to docs/CATALOGUE.md as `careeros name`: {missing}"
