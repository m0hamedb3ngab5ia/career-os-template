"""`careeros init`: give a fresh checkout its personal config/ and profile/.

    copy_examples(root)        # examples/profile -> profile, examples/config -> config (never overwrites)
    link_private(root, DIR)    # profile, config (+ CLAUDE.local.md) as symlinks into DIR (your private repo)

Both return an `InitReport` (what happened per path) and never touch a real directory or file that
already exists at the destination: copy leaves it alone, link refuses before changing anything.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from careeros.config import PERSONAL_DIRS, PKG_ROOT

LOCAL_NOTES = "CLAUDE.local.md"

# Shown after a copy: the files that carry personal values (marked `# EDIT` inside).
EDIT_HINTS: tuple[tuple[str, str], ...] = (
    ("profile/master.yaml", "identity, education, experience bullets (by id), skills, narratives"),
    ("profile/standard_answers.yaml", "every `answer` (work auth, school, links, phone, address) and the `eeo:` block"),
    ("profile/confidential_terms.yaml", "your employer's internal codenames / id patterns (QA hard-fails on them)"),
    ("profile/voice/samples/", "2-5 self-written letters or emails, then run /learn-voice"),
    ("config/targets.yaml", "candidate (level, graduation, min_base_usd, salary_dropdown_floor_usd), location"),
    ("config/companies.yaml", "dream_list, already_applied, blocklist (put your current employer there), boards"),
    ("config/categories.yaml", "bullet_priority: entry ids from your master.yaml"),
)


class InitError(Exception):
    """Refused: the destination holds real (non-symlink) personal data, or the source is missing."""


@dataclass
class InitReport:
    actions: list[tuple[str, str]] = field(default_factory=list)  # (path, what happened)

    def add(self, path: str, what: str) -> None:
        self.actions.append((path, what))

    def lines(self) -> list[str]:
        return [f"{what:<9} {path}" for path, what in self.actions]


def examples_dir(root: Path) -> Path:
    for cand in (root / "examples", PKG_ROOT / "examples"):
        if (cand / "config").is_dir() and (cand / "profile").is_dir():
            return cand
    raise InitError(f"no examples/ with config/ and profile/ under {root} or {PKG_ROOT}")


def copy_examples(root: Path) -> InitReport:
    root = Path(root)
    src = examples_dir(root)
    rep = InitReport()
    for name in PERSONAL_DIRS:
        dest = root / name
        if dest.exists() or dest.is_symlink():
            rep.add(f"{name}/", "kept")
            continue
        shutil.copytree(src / name, dest)
        rep.add(f"{name}/", "copied")
    return rep


def _link_plan(root: Path, private: Path) -> list[tuple[str, Path, Path]]:
    plan: list[tuple[str, Path, Path]] = []
    for name in PERSONAL_DIRS:
        target = private / name
        if not target.is_dir():
            raise InitError(f"{target} is not a directory; put your {name}/ there first (copy examples/{name})")
        plan.append((name, root / name, target))
    if (private / LOCAL_NOTES).is_file():
        plan.append((LOCAL_NOTES, root / LOCAL_NOTES, private / LOCAL_NOTES))
    return plan


def link_private(root: Path, private_dir: Path) -> InitReport:
    """Symlink profile/, config/ and CLAUDE.local.md (if present) from `private_dir` into `root`.

    Refuses (InitError, nothing changed) when any destination is a real file or directory.
    An existing symlink is replaced.
    """
    root = Path(root)
    private = Path(private_dir).expanduser().resolve()
    if not private.is_dir():
        raise InitError(f"{private} is not a directory")
    plan = _link_plan(root, private)
    real = [str(dest) for _, dest, _ in plan if dest.exists() and not dest.is_symlink()]
    if real:
        raise InitError(
            "refusing to replace real (non-symlink) paths: " + ", ".join(real)
            + ". Move them into your private directory first, then re-run `careeros init --link`."
        )
    rep = InitReport()
    for name, dest, target in plan:
        if dest.is_symlink():
            if dest.resolve() == target:
                rep.add(name, "linked")
                continue
            dest.unlink()
        dest.symlink_to(target, target_is_directory=target.is_dir())
        rep.add(name, "linked")
    return rep
