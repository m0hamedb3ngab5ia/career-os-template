"""Change keys in config YAML files without losing their comments, key order or layout (ruamel.yaml round
trip). Used by `careeros advise apply <id>` and the UI's Settings forms, only on an explicit call; nothing applies
advice by itself.

Lists and mappings keep their style: a flow list (`allow: [tier_c, tier_b]`) stays flow, and items of a block list
that survive an edit keep their end-of-line comments. A value equal to the current one is left untouched.

Writes go through symlinks (config/ may link into the candidate's private repo) to the real file, atomically,
and are rolled back when the result no longer validates.
"""
from __future__ import annotations

import difflib
import io
import os
from pathlib import Path
from typing import Any, Callable

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

_MISSING = object()


def _yaml() -> YAML:
    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    y.representer.add_representer(type(None), lambda r, _: r.represent_scalar("tag:yaml.org,2002:null", "null"))
    return y


def get_path(data: Any, dotted: str) -> Any:
    cur = data
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _write_atomic(real: Path, text: str) -> None:
    tmp = real.with_name(f".{real.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, real)


def keep_layout(original: str, dumped: str) -> str:
    """ruamel re-spaces aligned flow mappings (`small:  {a: 1}` -> `small: {a: 1}`). Keep every original line
    whose content (ignoring whitespace) is unchanged, so only the edited line differs."""
    o, n = original.splitlines(keepends=True), dumped.splitlines(keepends=True)
    sm = difflib.SequenceMatcher(a=[" ".join(x.split()) for x in o], b=[" ".join(x.split()) for x in n],
                                 autojunk=False)
    out: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        out.extend(o[i1:i2] if tag == "equal" else n[j1:j2])
    return "".join(out)


def _plain(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain(x) for x in v]
    return v


def _styled(new: Any, old: Any) -> Any:
    """`new` as ruamel nodes shaped like `old`: flow stays flow; surviving block-list items keep their comments."""
    if isinstance(new, dict):
        out = CommentedMap()
        for k, v in new.items():
            out[k] = _styled(v, old.get(k) if isinstance(old, dict) else None)
        if isinstance(old, CommentedMap):
            if old.fa.flow_style() or not old:  # `{}` in the file is flow by definition
                out.fa.set_flow_style()
            for k in out:
                if k in old.ca.items:
                    out.ca.items[k] = old.ca.items[k]
        return out
    if isinstance(new, list):
        out_s = CommentedSeq(_styled(v, None) for v in new)
        if isinstance(old, CommentedSeq):
            if old.fa.flow_style() or not old:
                out_s.fa.set_flow_style()
            used: set[int] = set()
            for i, v in enumerate(new):
                j = next((j for j, o in enumerate(old) if j not in used and _plain(o) == v), None)
                if j is not None:
                    used.add(j)
                    if j in old.ca.items:
                        out_s.ca.items[i] = old.ca.items[j]
        return out_s
    return new


def render_changes(original: str, changes: list[tuple[str, Any]]) -> tuple[str, dict[str, Any]]:
    """The file text after setting each (dotted, value), creating missing mappings, and the old values (None when
    absent). Pure: nothing is written."""
    y = _yaml()
    data = y.load(original) or CommentedMap()
    olds: dict[str, Any] = {}
    changed = False
    for dotted, value in changes:
        keys = dotted.split(".")
        cur = data
        for k in keys[:-1]:
            if not isinstance(cur.get(k), dict):
                cur[k] = CommentedMap()
            cur = cur[k]
        old = cur.get(keys[-1])
        olds[dotted] = _plain(old)
        if keys[-1] in cur and _plain(old) == value and type(_plain(old)) is type(value):
            continue
        cur[keys[-1]] = _styled(value, old)
        changed = True
    if not changed:
        return original, olds
    buf = io.StringIO()
    y.dump(data, buf)
    return keep_layout(original, buf.getvalue()), olds


def set_path(path: Path, dotted: str, value: Any) -> Any:
    """Set `dotted` (e.g. retention.unprepared_posting_days) to `value`, creating missing mappings. Returns
    the old value (None when absent)."""
    real = Path(os.path.realpath(path))
    original = real.read_text(encoding="utf-8")
    text, olds = render_changes(original, [(dotted, value)])
    if text != original:
        _write_atomic(real, text)
    return olds[dotted]


def preview_changes(path: Path, changes: list[tuple[str, Any]]) -> str:
    """Unified diff of what apply_changes would write ("" when nothing changes). Writes nothing."""
    real = Path(os.path.realpath(path))
    original = real.read_text(encoding="utf-8")
    text, _ = render_changes(original, changes)
    return "".join(difflib.unified_diff(original.splitlines(keepends=True), text.splitlines(keepends=True),
                                        fromfile=f"{Path(path).name} (now)", tofile=f"{Path(path).name} (after)"))


def apply_changes_many(changes: dict[Path, list[tuple[str, Any]]], *,
                       validate: Callable[[list[Path]], None]) -> dict[Path, dict[str, Any]]:
    """Write every file's changes, then `validate(real paths)`; on any error restore every file's original text.
    Returns {path: {dotted: old value}}."""
    reals = {p: Path(os.path.realpath(p)) for p in changes}
    originals = {p: reals[p].read_text(encoding="utf-8") for p in changes}
    olds: dict[Path, dict[str, Any]] = {}
    written: list[Path] = []
    try:
        for p, ch in changes.items():
            text, olds[p] = render_changes(originals[p], ch)
            if text != originals[p]:
                _write_atomic(reals[p], text)
                written.append(p)
        validate(list(reals.values()))
    except BaseException:
        for p in written:
            _write_atomic(reals[p], originals[p])
        raise
    return olds


def apply_changes(path: Path, changes: list[tuple[str, Any]], *, validate: Callable[[Path], None]) -> dict[str, Any]:
    """apply_changes_many for one file: all keys land together or none do. Returns {dotted: old value}."""
    return apply_changes_many({path: changes}, validate=lambda reals: validate(reals[0]))[path]


def apply_change(path: Path, dotted: str, value: Any, *, validate: Callable[[Path], None],
                 expect_from: Any = _MISSING, current: Callable[[Any], Any] | None = None) -> Any:
    """set_path + validate, restoring the original text when validation raises. `expect_from`: refuse when the
    current value differs (the recommendation was computed against an older file). `current(data)` gives the
    effective value (defaults applied) to compare with; default: the raw YAML value."""
    real = Path(os.path.realpath(path))
    original = real.read_text(encoding="utf-8")
    data = _yaml().load(original)
    current = current(data) if current else get_path(data, dotted)
    if expect_from is not _MISSING and current != expect_from:
        raise ValueError(f"{dotted} is now {current!r}, not {expect_from!r}; run `careeros advise` again")
    old = set_path(real, dotted, value)
    try:
        validate(real)
    except BaseException:
        _write_atomic(real, original)
        raise
    return old
