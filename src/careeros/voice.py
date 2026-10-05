"""Profile › Writing samples (REQ-101): files in profile/voice/samples/ and the style guide's `## Learned` section
that the learn-voice skill writes."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from careeros.runs.yamledit import _write_atomic

EXTS = (".txt", ".md", ".pdf", ".docx")
MAX_BYTES = 5 * 1024 * 1024
_LEARNED = re.compile(r"(^## Learned[^\n]*\n)(.*?)(?=^## |\Z)", re.M | re.S)


class Unsupported(ValueError):
    pass


def samples_dir(root: Path) -> Path:
    return root / "profile" / "voice" / "samples"


def _guide(root: Path) -> Path:
    return root / "profile" / "voice" / "style_guide.md"


def _path(root: Path, name: str) -> Path:
    if not name or name.startswith(".") or Path(name).name != name or "\\" in name:
        raise ValueError(f"invalid sample name {name!r}")
    return samples_dir(root) / name


def list_samples(root: Path) -> list[dict[str, Any]]:
    d = samples_dir(root)
    return [{"name": p.name, "size": p.stat().st_size} for p in sorted(d.iterdir())
            if p.is_file() and not p.name.startswith(".")] if d.is_dir() else []


def add_sample(root: Path, name: str, data: bytes) -> dict[str, Any]:
    p = _path(root, name)
    if p.suffix.lower() not in EXTS:
        raise Unsupported(f"{name}: only {', '.join(EXTS)} files")
    if len(data) > MAX_BYTES:
        raise ValueError(f"{name}: larger than 5 MB")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return {"name": p.name, "size": len(data)}


def remove_sample(root: Path, name: str) -> None:
    p = _path(root, name)
    if not p.is_file():
        raise KeyError(name)
    p.unlink()


def learned(root: Path) -> str:
    g = _guide(root)
    m = _LEARNED.search(g.read_text(encoding="utf-8")) if g.exists() else None
    return m.group(2).strip() if m else ""


def clear_learned(root: Path) -> None:
    """UC-005 alt: the last sample is gone, so the learned style no longer has a source."""
    g = _guide(root)
    if g.exists():
        text = g.read_text(encoding="utf-8")
        _write_atomic(g, _LEARNED.sub(lambda m: m.group(1), text, count=1))
