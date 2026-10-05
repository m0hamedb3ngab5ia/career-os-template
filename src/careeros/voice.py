"""Profile › Writing samples (REQ-101): files in profile/voice/samples/ and the style guide's `## Learned` section
that the learn-voice skill writes."""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree
from typing import Any

from careeros.runs.yamledit import _write_atomic

EXTS = (".txt", ".md", ".eml", ".pdf", ".docx")  # .docx is stored as .txt; the rest as-is for learn-voice to Read
MAX_BYTES = 5 * 1024 * 1024
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
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


def docx_text(data: bytes) -> str:
    """Plain text of a .docx (stdlib only): one line per paragraph, tabs and line breaks kept."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if z.getinfo("word/document.xml").file_size > 4 * MAX_BYTES:  # zip bomb guard
                raise ValueError("document too large")
            body = ElementTree.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as e:
        raise ValueError(f"not a valid .docx ({e})") from None
    tags = {_W + "t": None, _W + "tab": "\t", _W + "br": "\n", _W + "cr": "\n"}
    return "\n".join("".join((e.text or "") if tags[e.tag] is None else tags[e.tag]
                              for e in para.iter() if e.tag in tags)
                      for para in body.iter(_W + "p"))


def add_sample(root: Path, name: str, data: bytes) -> dict[str, Any]:
    p = _path(root, name)
    if p.suffix.lower() not in EXTS:
        raise Unsupported(f"{name}: only {', '.join(EXTS)} files")
    if len(data) > MAX_BYTES:
        raise ValueError(f"{name}: larger than 5 MB")
    if p.suffix.lower() == ".docx":
        try:
            data = docx_text(data).encode("utf-8")
        except ValueError as e:
            raise ValueError(f"{name}: {e}") from None
        p, name = p.with_suffix(".txt"), Path(name).stem + ".txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 1
    while p.exists():  # never overwrite an existing sample: letter.md -> letter-2.md
        n += 1
        p = p.with_name(f"{Path(name).stem}-{n}{Path(name).suffix}")
    _write_atomic(p, data)
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
