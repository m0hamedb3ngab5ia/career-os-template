"""Change keys in config YAML files without losing their comments, key order or layout (ruamel.yaml round
trip). Used by `careeros advise apply <id>` and the UI's Settings forms, only on an explicit call; nothing applies
advice by itself.

Lists and mappings keep their style: a flow list (`allow: [tier_c, tier_b]`) stays flow, and items of a block list
that survive an edit keep their end-of-line comments. A value equal to the current one is left untouched.
Strings are quoted whenever PyYAML (the YAML 1.1 reader every loader uses) would read them back as something else:
"10:30" (sexagesimal 630), off / yes (booleans), "12" (an int).

Writes go through symlinks (config/ may link into the candidate's private repo) to the real file, atomically,
and are rolled back when the result no longer validates.
"""
from __future__ import annotations

import difflib
import io
import os
from pathlib import Path
from typing import Any, Callable

import re

import yaml as pyyaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import DoubleQuotedScalarString, ScalarString

_MISSING = object()


_BLOCK_ITEM = re.compile(r"^( *)- ")
_KEY_LINE = re.compile(r"^( *)[^\s#-][^#]*:\s*(#.*)?$")


def _seq_offset(text: str) -> int:
    """How far this file indents `- item` under its key: 2 (`key:` then `  - item`, the examples' style) or 0
    (`- item` level with the key, PyYAML's style). The first block list decides."""
    lines = text.splitlines()
    for prev, line in zip(lines, lines[1:]):
        k, m = _KEY_LINE.match(prev), _BLOCK_ITEM.match(line)
        if k and m:
            return 0 if len(m.group(1)) == len(k.group(1)) else 2
    return 2


def _yaml(offset: int = 2) -> YAML:
    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=offset + 2, offset=offset)
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
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, real)
    finally:
        tmp.unlink(missing_ok=True)


_COMMENT_GAP = re.compile(r"\s+#")


def _loose(line: str) -> str:
    """ruamel re-spaces aligned flow mappings and end-of-line comments; ignore that spacing (only)."""
    body, sep, comment = line.partition(" #")
    body = re.sub(r"^\s+|\s+$", "", body)
    body = re.sub(r"^((?:- )*[^\s:'\"]+:)\s+", r"\1 ", body)      # `small:  {a: 1}` -> `small: {a: 1}`
    return body + (" #" + comment.strip() if sep else "")


def _merge(o: list[str], n: list[str], norm) -> str:
    sm = difflib.SequenceMatcher(a=[norm(x) for x in o], b=[norm(x) for x in n], autojunk=False)
    out: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        out.extend(o[i1:i2] if tag == "equal" else n[j1:j2])
    return "".join(out)


def _same_data(a: str, b: str) -> bool:
    try:
        return _plain(_yaml().load(a)) == _plain(_yaml().load(b))
    except Exception:  # noqa: BLE001 - an unparsable merge is simply not the same data
        return False


def keep_layout(original: str, dumped: str) -> str:
    """Keep every original line whose content is unchanged (ignoring indentation-style re-spacing), so only the
    edited lines differ. If that would lose an edit (one that only changed whitespace inside a value), fall back to
    comparing lines exactly, and in the last resort to ruamel's own output."""
    o, n = original.splitlines(keepends=True), dumped.splitlines(keepends=True)
    for norm in (_loose, lambda x: x.rstrip("\n")):
        merged = _merge(o, n, norm)
        if _same_data(merged, dumped):
            return merged
    return dumped


def _plain(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain(x) for x in v]
    return v


def _needs_quotes(s: str) -> bool:
    try:
        return pyyaml.safe_load(s) != s
    except pyyaml.YAMLError:
        return True


def has_ambiguous_plain(node: Any) -> bool:
    """A plain (unquoted) string somewhere in `node` that PyYAML reads as something else (`off`, 10:30)."""
    if isinstance(node, dict):
        return any(has_ambiguous_plain(k) or has_ambiguous_plain(v) for k, v in node.items())
    if isinstance(node, list):
        return any(has_ambiguous_plain(v) for v in node)
    return isinstance(node, str) and not isinstance(node, ScalarString) and _needs_quotes(node)


def _scalar(new: str, old: Any) -> Any:
    if isinstance(old, ScalarString):
        return type(old)(new)  # keep the file's quote style
    return DoubleQuotedScalarString(new) if _needs_quotes(new) else new


def _styled(new: Any, old: Any) -> Any:
    """`new` as ruamel nodes shaped like `old`: flow stays flow; surviving block-list items keep their comments;
    strings PyYAML would misread are quoted."""
    if isinstance(new, str):
        return _scalar(new, old)
    if isinstance(new, dict):
        out = CommentedMap()
        old_keys = {str(k): k for k in old} if isinstance(old, dict) else {}
        for k, v in new.items():
            key = old_keys.get(str(k), k)
            if isinstance(key, str) and not isinstance(key, ScalarString) and (key not in old_keys.values()
                                                                               or _needs_quotes(key)):
                key = _scalar(str(key), None)  # a new key, or an old unquoted one PyYAML misreads (ON -> true)
            out[key] = _styled(v, old.get(key) if isinstance(old, dict) else None)
        if isinstance(old, CommentedMap):
            if old.fa.flow_style() or not old:  # `{}` in the file is flow by definition
                out.fa.set_flow_style()
            for k in out:
                if k in old.ca.items:
                    out.ca.items[k] = old.ca.items[k]
        return out
    if isinstance(new, list):
        olds = list(old) if isinstance(old, list) else []
        used: set[int] = set()
        items = []
        matches: dict[int, int] = {}
        for i, v in enumerate(new):
            j = next((j for j, o in enumerate(olds) if j not in used and _plain(o) == v), None)
            if j is not None:
                used.add(j)
                matches[i] = j
            items.append(_styled(v, olds[j] if j is not None else None))
        out_s = CommentedSeq(items)
        if isinstance(old, CommentedSeq):
            if old.fa.flow_style() or not old:
                out_s.fa.set_flow_style()
            for i, j in matches.items():
                if j in old.ca.items:
                    out_s.ca.items[i] = old.ca.items[j]
        return out_s
    return new


def render_changes(original: str, changes: list[tuple[str, Any]]) -> tuple[str, dict[str, Any]]:
    """The file text after setting each (dotted, value), creating missing mappings, and the old values (None when
    absent). Pure: nothing is written."""
    y = _yaml(_seq_offset(original))  # keep the file's list indentation (PyYAML writes `- item` level with key)
    data = y.load(original) or CommentedMap()
    olds: dict[str, Any] = {}
    changed = False
    for dotted, value in changes:
        keys = dotted.split(".")
        cur = data
        for i, k in enumerate(keys[:-1]):
            if not isinstance(cur, dict):
                raise ValueError(f"{'.'.join(keys[:i])} is a list, not a mapping; can't set {dotted}")
            if not isinstance(cur.get(k), dict):
                if k in cur and cur[k] is not None:
                    raise ValueError(f"{'.'.join(keys[:i + 1])} is not a mapping; can't set {dotted}")
                cur[k] = CommentedMap()
            cur = cur[k]
        if not isinstance(cur, dict):
            raise ValueError(f"can't set {dotted}: its parent is not a mapping")
        old = cur.get(keys[-1])
        olds[dotted] = _plain(old)
        if (keys[-1] in cur and _plain(old) == value and type(_plain(old)) is type(value)
                and not has_ambiguous_plain(old)):  # same value, but unquoted `off` / 10:30: rewrite it quoted
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
    texts: dict[Path, str] = {}
    for p, ch in changes.items():  # render everything first: a bad key path writes nothing
        texts[p], olds[p] = render_changes(originals[p], ch)
    try:
        for p in changes:
            if texts[p] != originals[p]:
                written.append(p)
                _write_atomic(reals[p], texts[p])
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
