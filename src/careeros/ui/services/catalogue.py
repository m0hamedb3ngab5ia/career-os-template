"""docs/CATALOGUE.md as JSON for the Catalogue view (REQ-165). Tables only; inline `code` stays as backticked text."""
from __future__ import annotations

import re

from pydantic import BaseModel


class CatalogueRow(BaseModel):
    feature: str
    what: str
    how: str
    req: str


class CatalogueSection(BaseModel):
    title: str
    rows: list[CatalogueRow]
    notes: list[str] = []  # prose lines outside tables (e.g. "Start here")


class Catalogue(BaseModel):
    intro: list[str]
    sections: list[CatalogueSection]


def _cells(line: str) -> list[str]:
    """Split a table line on `|` outside backticks (outer pipes dropped)."""
    out, cur, code = [], "", False
    for ch in line.strip().removeprefix("|").removesuffix("|"):
        code ^= ch == "`"
        if ch == "|" and not code:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    return [*out, cur.strip()]


def _plain(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # [text](url) -> text
    return text.replace("**", "").replace("\\|", "|")  # bold markers; markdown-escaped pipe


def parse_catalogue(md: str) -> Catalogue:
    intro: list[str] = []
    sections: list[CatalogueSection] = []
    cur: CatalogueSection | None = None
    header_seen = False
    for raw in md.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            cur = CatalogueSection(title=line[3:].strip(), rows=[])
            sections.append(cur)
            header_seen = False
        elif cur is None:
            if line.strip() and not line.startswith("#"):
                intro.append(_plain(line.strip()))
        elif line.startswith("|"):
            if not header_seen:
                header_seen = True  # the column names
                continue
            cells = [_plain(c) for c in _cells(line)]
            if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                continue
            cells += [""] * (4 - len(cells))
            cur.rows.append(CatalogueRow(feature=cells[0], what=cells[1], how=cells[2], req=cells[3]))
        elif line.strip():
            cur.notes.append(_plain(line.strip()))
    return Catalogue(intro=intro, sections=[s for s in sections if s.rows or s.notes])
