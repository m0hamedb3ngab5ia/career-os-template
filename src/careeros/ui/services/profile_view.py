"""Read-only Profile and Settings views for the sidebar pages. Nothing here writes; credentials never appear."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from careeros import resumes as resume_store
from careeros.config import Settings
from careeros.ui.services import settings_io
from careeros.ui.settings_schema import SECTIONS
from careeros.ui.settings_schema.model import Field

_HIDDEN = ("credential", "password", "secret", "token", "api_key")


class ResumeRow(BaseModel):
    rid: str
    name: str
    type: str
    version: int
    at: str


class DocumentRow(BaseModel):
    name: str
    size: int


class AnswerRow(BaseModel):
    key: str
    answer: str


class Profile(BaseModel):
    resumes: list[ResumeRow]
    documents: list[DocumentRow]
    answers: list[AnswerRow]


class SettingRow(BaseModel):
    label: str
    value: str
    help: str = ""


class SettingGroup(BaseModel):
    title: str
    rows: list[SettingRow]


class SettingSection(BaseModel):
    id: str
    title: str
    groups: list[SettingGroup]


class SettingsView(BaseModel):
    sections: list[SettingSection]


def _text(v: Any) -> str:
    if v is None or v == "" or v == []:
        return "Not set"
    if v is True:
        return "Yes"
    if v is False:
        return "No"
    if isinstance(v, (list, tuple)):
        return ", ".join(_text(i) for i in v)
    if isinstance(v, dict):
        return ", ".join(f"{k}: {_text(i)}" for k, i in v.items())
    return str(v)


def profile(settings: Settings) -> Profile:
    root = settings.root
    resumes = [ResumeRow(rid=r["rid"], name=r["name"], type=r["type"], version=r["latest"], at=r["at"])
               for r in resume_store.list_resumes(root)]
    docs_dir = root / "profile" / "documents"
    documents = [DocumentRow(name=p.name, size=p.stat().st_size)
                 for p in sorted(docs_dir.iterdir()) if p.is_file() and not p.name.startswith(".")] \
        if docs_dir.is_dir() else []
    answers = [AnswerRow(key=str(a.get("key", "")), answer=_text(a.get("answer")))
               for a in (settings.standard_answers.get("answers") or []) if isinstance(a, dict) and a.get("key")]
    return Profile(resumes=resumes, documents=documents, answers=answers)


def _shown(f: Field) -> bool:
    return not any(w in f.key.lower() for w in _HIDDEN)


def settings_view(settings: Settings) -> SettingsView:
    out: list[SettingSection] = []
    for sec in SECTIONS:
        if sec.advanced:
            continue
        try:
            values = settings_io.read_section(settings, sec.id)["values"]
        except (OSError, ValueError):
            continue
        groups = []
        for g in sec.groups:
            if g.advanced:
                continue
            rows = [SettingRow(label=f.label, value=_text(values.get(f.id)), help=f.help)
                    for f in g.fields() if _shown(f)]
            if rows:
                groups.append(SettingGroup(title=g.title, rows=rows))
        if groups:
            out.append(SettingSection(id=sec.id, title=sec.title, groups=groups))
    return SettingsView(sections=out)


__all__ = ["Profile", "SettingsView", "profile", "settings_view"]
