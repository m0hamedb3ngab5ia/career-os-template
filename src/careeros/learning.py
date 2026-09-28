"""The system gets smarter with every application.

* `learn_answer`: a question the human answered once (Action Item, UI, or `careeros learn answer`) becomes an
  entry in profile/standard_answers.yaml (general `answers:`, a company-only `company_answers: {<Company>: [...]}`
  block, or an `eeo:` value), so the next apply-job fills it without asking. The file is edited with the same
  round-trip YAML the Settings forms use: comments, order and `# INSERT` markers survive.
* `learn_lesson` / `lessons_for`: hurdles hit on an ATS or at a company go to profile/apply_lessons.yaml and are
  read back by apply-job at session start ("Known hurdles").

Both refuse to write into examples/ (the fictional candidate's files are documentation, never a target).
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover (Windows)
    fcntl = None  # type: ignore[assignment]

from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import DoubleQuotedScalarString as DQ

from careeros.config import Settings
from careeros.runs.yamledit import _seq_offset, _write_atomic, _yaml

SCOPES = ("general", "company")
LESSON_KEYS = ("id", "text", "ats", "company", "job_id", "added", "tags")


def slug(text: str, fallback: str = "question") -> str:
    s = re.sub(r"[^a-z0-9]+", "_", re.sub(r"['\u2019]", "", (text or "").lower())).strip("_")
    return s[:60].rstrip("_") or fallback


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


_PREFIX_RE = re.compile(r"^[a-z_]+(?: [a-z_ ]+)?:\s+", re.I)   # "legal question not in standard answers: "
_LIMIT_RE = re.compile(r"\s*\(limit \d+\)\s*$", re.I)
_QUOTED_RE = re.compile(r'^"([^"]{3,})"$')
_URGENT_RE = re.compile(r"\s+\u2014\s+urgent:.*$", re.I)   # " — <gate action_note>" on urgent items


def question_pattern(question: str) -> str:
    """A regex that hits the question itself (whitespace-insensitive, punctuation escaped); the default `match`."""
    return r"\s+".join(re.escape(w) for w in normalize(question).split())


def question_from_action(what: str) -> str:
    """The exact form question inside an Action Item's "What to do" text (the apply-job / answer-question
    contract: `<class>: <question> (limit n)`, `legal question not in standard answers: <question>`, or the
    question quoted)."""
    t = _LIMIT_RE.sub("", _URGENT_RE.sub("", normalize(what)))
    t = _PREFIX_RE.sub("", t, count=1).strip()
    m = _QUOTED_RE.match(t)   # only a wholly quoted payload; quotes inside the question stay
    return m.group(1).strip() if m else t


_THREAD_LOCK = threading.Lock()


@contextmanager
def _locked(real: Path) -> Iterator[None]:
    """Serialize a whole read-modify-write of the learning files (threads and processes)."""
    with _THREAD_LOCK:
        if fcntl is None:  # pragma: no cover
            yield
            return
        with real.parent.joinpath(".learning.lock").open("a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)


def _guard_path(p: Path) -> Path:
    from careeros.config import PKG_ROOT

    real = Path(os.path.realpath(p))
    if real.is_relative_to(Path(os.path.realpath(PKG_ROOT / "examples"))):
        raise ValueError(f"refusing to write into examples/: {p} (run `careeros init` first)")
    return real


_EEO_KEY_RE = re.compile(r"^[a-z0-9_]+$")
_BAD_JOB_ID_RE = re.compile(r"^\s*$|[/\\\\]|\.\.|^\.")


def _check_job_id(job_id: str) -> str:
    """A job id names one folder under jobs_dir: no separators, `..` or leading dot."""
    if _BAD_JOB_ID_RE.search(job_id):
        raise ValueError(f"invalid job_id {job_id!r}")
    return job_id


def _yaml_key(company: str) -> str:
    """`company` as a YAML mapping key: plain when safe, JSON/double-quoted otherwise (`Acme, #1`)."""
    return company if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._'&()/-]*[A-Za-z0-9.)]", company) else json.dumps(company)


def answers_path(settings: Settings) -> Path:
    return Path(settings.paths.get("standard_answers") or settings.root / "profile" / "standard_answers.yaml")


def lessons_path(settings: Settings) -> Path:
    return Path(settings.paths.get("apply_lessons") or answers_path(settings).parent / "apply_lessons.yaml")


def _load_rt(real: Path) -> tuple[Any, CommentedMap]:
    text = real.read_text(encoding="utf-8") if real.exists() else ""
    y = _yaml(_seq_offset(text) if text else 2)
    data = y.load(text) if text.strip() else None
    if data is None:
        data = CommentedMap()
    if not isinstance(data, dict):
        raise ValueError(f"{real.name}: top level must be a mapping")
    return y, data


def _dump(y: Any, data: CommentedMap, real: Path) -> None:
    import io

    buf = io.StringIO()
    y.dump(data, buf)
    _write_atomic(real, buf.getvalue())


def _entry(question: str, answer: str, key: str | None, match: list[str] | None, note: str) -> CommentedMap:
    q = normalize(question)
    e = CommentedMap()
    e["key"] = key or slug(q)
    e["match"] = CommentedSeq([DQ(m) for m in (list(match) if match else [question_pattern(q)])])
    e["match"].fa.set_flow_style()
    e["answer"] = DQ(answer)
    e["note"] = DQ(note)
    return e


def _all_keys(data: dict[str, Any], company: str | None = None) -> set[str]:
    """Keys a new entry must not reuse: general answers plus every company's (general scope) or plus only
    `company`'s (company scope: the same generic question may be learned once per company)."""
    keys = {str(x.get("key")) for x in (data.get("answers") or []) if isinstance(x, dict)}
    ca = data.get("company_answers") if isinstance(data.get("company_answers"), dict) else {}
    for co, lst in ca.items():
        if company is None or str(co).strip().lower() == company.strip().lower():
            keys |= {str(x.get("key")) for x in (lst if isinstance(lst, list) else []) if isinstance(x, dict)}
    return keys


_TOP_KEY_RE = re.compile(r"^[A-Za-z_][^\s:#]*:")


def _block_end(lines: list[str], start: int) -> int:
    """Index just past the last content line of the block that starts at `lines[start]` (a top-level key); the
    trailing blank and comment lines stay with whatever follows (they introduce the next block)."""
    end = start + 1
    for i in range(start + 1, len(lines)):
        if _TOP_KEY_RE.match(lines[i]):
            break
        if lines[i].strip() and not lines[i].lstrip().startswith("#"):
            end = i + 1
    return end


def _render(y: Any, node: Any) -> str:
    import io

    buf = io.StringIO()
    y.dump(node, buf)
    return buf.getvalue()


def _insert_entry(text: str, e: CommentedMap, *, company: str | None) -> str:
    """Append `e` to `answers:` (or `company_answers: {company: [...]}`) by editing the text, so every other line
    (comments, `# INSERT` markers, the eeo block's indentation) stays byte-for-byte."""
    offset = _seq_offset(text) if text.strip() else 2
    y = _yaml(offset)
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    item = _render(y, CommentedSeq([e]))                       # "  - key: ...\n    match: ...\n"
    if company is None:
        start = next((i for i, ln in enumerate(lines) if ln.startswith("answers:")), None)
        if start is None:
            return "".join(lines) + "\nanswers:\n" + item
        lines.insert(_block_end(lines, start), item)
        return "".join(lines)
    start = next((i for i, ln in enumerate(lines) if ln.startswith("company_answers:")), None)
    if start is None:
        block = CommentedMap(); block[company] = CommentedSeq([e])
        return "".join(lines) + "\n" + _render(y, CommentedMap({"company_answers": block}))
    end = _block_end(lines, start)
    forms = (company, json.dumps(company), "'" + company.replace("'", "''") + "'")  # plain, "quoted", 'quoted'
    key_rx = re.compile(r"^(\s+)(?:" + "|".join(re.escape(f) for f in forms) + r")\s*:")
    ci = next((i for i in range(start + 1, end) if key_rx.match(lines[i])), None)
    indent = " " * (len(key_rx.match(lines[ci]).group(1)) if ci is not None else 2)
    item = "".join(indent + ln if ln.strip() else ln for ln in item.splitlines(keepends=True))
    if ci is None:
        lines.insert(end, f"{indent}{_yaml_key(company)}:\n" + item)
        return "".join(lines)
    cend = end
    for i in range(ci + 1, end):
        if re.match(r"^" + indent + r"[^\s-]", lines[i]):
            cend = i
            break
    lines.insert(cend, item)
    return "".join(lines)


def learn_answer(settings: Settings, *, question: str, answer: str, job_id: str | None = None,
                 key: str | None = None, match: list[str] | None = None, scope: str = "general",
                 company: str | None = None, eeo: bool = False) -> dict[str, Any]:
    """Append one learned answer to profile/standard_answers.yaml and, with `job_id`, record it in that job's
    answers.json (needs_review false, source "learned"). Returns the entry as written plus `scope`/`company`."""
    q, a = normalize(question), (answer or "").strip()
    if not q:
        raise ValueError("question is empty")
    if not a:
        raise ValueError("answer is empty; nothing learned")
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {', '.join(SCOPES)}")
    if company:
        scope = "company"
    if scope == "company" and not company:
        raise ValueError("scope company needs --company <name>")
    for pat in match or []:
        try:
            re.compile(pat, re.I)
        except re.error as e:
            raise ValueError(f"match {pat!r} is not a valid regex ({e})") from None
    if job_id:
        _check_job_id(job_id)
    real = _guard_path(answers_path(settings))
    real.parent.mkdir(parents=True, exist_ok=True)
    with _locked(real):
        return _learn_answer_locked(settings, real, q, a, job_id, key, match, scope, company, eeo)


def _learn_answer_locked(settings: Settings, real: Path, q: str, a: str, job_id: str | None, key: str | None,
                         match: list[str] | None, scope: str, company: str | None, eeo: bool) -> dict[str, Any]:
    import yaml as pyyaml

    if job_id:
        _load_answers_json(_job_dir(settings, job_id) / "answers.json")  # refuse before writing anything
    text = real.read_text(encoding="utf-8") if real.exists() else ""
    try:
        data = pyyaml.safe_load(text) or {}
    except pyyaml.YAMLError as e:
        raise ValueError(f"{real.name}: not a single mapping ({e}); convert to answers:/eeo: shape") from None
    if not isinstance(data, dict):
        raise ValueError(f"{real.name}: not a single mapping; convert to answers:/eeo: shape")
    note = f"learned {date.today().isoformat()}" + (f" from job {job_id}" if job_id else "")
    if eeo:
        from careeros.runs.yamledit import set_path

        k = key or slug(q)
        if not _EEO_KEY_RE.match(k):
            raise ValueError(f"eeo key {k!r} must match a-z0-9_ (no dots)")
        set_path(real, f"eeo.{k}.answer", a)
        entry: dict[str, Any] = {"key": k, "answer": a, "note": note, "eeo": True}
    else:
        e = _entry(q, a, key, match, note)
        co = company if scope == "company" else None
        if e["key"] in _all_keys(data, co):
            raise ValueError(f"key {e['key']!r} already exists in {real.name}; pass --key for a new one")
        out = _insert_entry(text, e, company=company if scope == "company" else None)
        check = pyyaml.safe_load(out)
        if not isinstance(check, dict) or e["key"] not in _all_keys(check, co):
            raise ValueError(f"{real.name}: could not append the entry safely; add it by hand")
        _write_atomic(real, out)
        entry = {"key": e["key"], "match": list(e["match"]), "answer": a, "note": note}
    from careeros.apply.questions import clear_cache

    clear_cache()
    entry.update({"scope": "eeo" if eeo else scope, "company": company, "question": q})
    if job_id:
        entry["answers_json"] = record_answer(settings, job_id, q, a, entry["key"])
    return entry


def _job_dir(settings: Settings, job_id: str) -> Path:
    return Path(settings.paths.get("jobs_dir") or settings.root / "data" / "jobs") / _check_job_id(job_id)


def _load_answers_json(p: Path) -> list[Any]:
    """The job's answers.json list ([] when missing); ValueError (nothing written) when it is damaged."""
    if not p.exists():
        return []
    try:
        items = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{p.parent.name}/answers.json is not valid JSON ({e}); fix it by hand first") from None
    if not isinstance(items, list):
        raise ValueError(f"{p.parent.name}/answers.json must be a list; fix it by hand first")
    return items


def record_answer(settings: Settings, job_id: str, question: str, answer: str, key: str) -> bool:
    """Set the matching answers.json entry (or add one) to the learned answer. False when the job dir is missing."""
    d = _job_dir(settings, job_id)
    if not d.is_dir():
        return False
    p = d / "answers.json"
    items = _load_answers_json(p)
    want = normalize(question).lower()
    now = datetime.now().isoformat(timespec="seconds")
    hit = next((x for x in items if isinstance(x, dict) and normalize(str(x.get("question") or "")).lower() == want), None)
    if hit is None:
        hit = {"question": question, "class": "standard"}
        items.append(hit)
    hit.update({"answer": answer, "type": "standard", "standard_key": key, "needs_review": False,
                "action_item": None, "source": "learned", "answered_at": now})
    _write_atomic(p, json.dumps(items, indent=2, ensure_ascii=False) + "\n")
    return True


# --- lessons ------------------------------------------------------------------------------------------------

def _lesson(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or not str(raw.get("text") or "").strip():
        return None
    out = {k: raw.get(k) for k in LESSON_KEYS}
    out["id"] = str(out["id"] or "")
    out["text"] = str(out["text"]).strip()
    out["ats"] = str(out["ats"]).lower() if out["ats"] else None
    out["company"] = str(out["company"]) if out["company"] else None
    out["job_id"] = str(out["job_id"]) if out["job_id"] else None
    out["added"] = str(out["added"]) if out["added"] else None
    out["tags"] = [str(t) for t in (out["tags"] or [])] if isinstance(out["tags"], list) else []
    return out


def load_lessons(settings: Settings) -> list[dict[str, Any]]:
    import yaml

    p = lessons_path(settings)
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    raw = data.get("lessons") if isinstance(data, dict) else None
    return [x for x in (_lesson(r) for r in (raw or [])) if x]


def lessons_for(settings: Settings, ats: str | None = None, company: str | None = None) -> list[dict[str, Any]]:
    """General lessons plus those for this ATS and this company (case-insensitive), file order."""
    a, c = (ats or "").lower() or None, (company or "").lower() or None
    return [x for x in load_lessons(settings)
            if (x["ats"] is None or x["ats"] == a) and (x["company"] is None or x["company"].lower() == c)]


def learn_lesson(settings: Settings, *, text: str, ats: str | None = None, company: str | None = None,
                 job_id: str | None = None, tags: tuple[str, ...] | list[str] = ()) -> dict[str, Any]:
    """Append one lesson to profile/apply_lessons.yaml (created when missing). Returns it."""
    t = normalize(text)
    if not t:
        raise ValueError("lesson text is empty")
    real = _guard_path(lessons_path(settings))
    real.parent.mkdir(parents=True, exist_ok=True)
    with _locked(real):
        return _learn_lesson_locked(real, t, ats, company, job_id, tags)


def _learn_lesson_locked(real: Path, t: str, ats: str | None, company: str | None, job_id: str | None,
                         tags: tuple[str, ...] | list[str]) -> dict[str, Any]:
    y, data = _load_rt(real)
    lst = data.get("lessons")
    if not isinstance(lst, list):
        lst = data["lessons"] = CommentedSeq()
    e = CommentedMap()
    e["id"] = uuid.uuid4().hex[:8]
    e["text"] = DQ(t)
    e["ats"] = (ats or "").lower() or None
    e["company"] = company or None
    e["job_id"] = job_id or None
    e["added"] = date.today().isoformat()
    e["tags"] = CommentedSeq([str(x) for x in tags])
    e["tags"].fa.set_flow_style()
    lst.append(e)
    _dump(y, data, real)
    return _lesson(dict(e)) or {}


# --- Action Items --------------------------------------------------------------------------------------------

LEARNABLE_TYPES = ("question", "salary")


def learn_from_action(settings: Settings, tracker: Any, aid: str, answer: str, *, scope: str = "general",
                      company: str | None = None, item: dict[str, Any] | None = None) -> dict[str, Any]:
    """`careeros action done <id> --answer` / POST /actions/{id}/answer: the question is the item's "What to do"
    text, the job its JobID. `item` may be passed (UI index row); else the tracker's open items are searched."""
    if item is None:
        rows = {str(r.get("ID")): r for r in tracker.list_action_items(open_only=False)}
        r = rows.get(aid)
        if r is None:
            raise LookupError(f"no action item {aid!r}")
        item = {"type": r.get("Type"), "what": r.get("What to do"), "job_id": r.get("JobID"), "company": r.get("Company")}
    if str(item.get("type") or "") not in LEARNABLE_TYPES:
        raise ValueError(f"only a {' / '.join(LEARNABLE_TYPES)} item can be answered (this one is {item.get('type')!r})")
    if scope == "company" and not company:
        company = str(item.get("company") or "") or None
        if not company:
            raise ValueError("scope company needs a company (the item has none)")
    return learn_answer(settings, question=question_from_action(str(item.get("what") or "")), answer=answer,
                        job_id=str(item.get("job_id") or "") or None, scope=scope, company=company)
