"""Change one key in a config YAML file without losing its comments, key order or layout (ruamel.yaml round
trip). Used only by `careeros advise apply <id>`, on an explicit call; nothing applies advice by itself.

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
from ruamel.yaml.comments import CommentedMap

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


def set_path(path: Path, dotted: str, value: Any) -> Any:
    """Set `dotted` (e.g. retention.unprepared_posting_days) to `value`, creating missing mappings. Returns
    the old value (None when absent)."""
    real = Path(os.path.realpath(path))
    y = _yaml()
    original = real.read_text(encoding="utf-8")
    data = y.load(original) or CommentedMap()
    keys = dotted.split(".")
    cur = data
    for k in keys[:-1]:
        if not isinstance(cur.get(k), dict):
            cur[k] = CommentedMap()
        cur = cur[k]
    old = cur.get(keys[-1])
    cur[keys[-1]] = value
    buf = io.StringIO()
    y.dump(data, buf)
    _write_atomic(real, keep_layout(original, buf.getvalue()))
    return old


def apply_change(path: Path, dotted: str, value: Any, *, validate: Callable[[Path], None],
                 expect_from: Any = _MISSING) -> Any:
    """set_path + validate, restoring the original text when validation raises. `expect_from`: refuse when the
    current value differs (the recommendation was computed against an older file)."""
    real = Path(os.path.realpath(path))
    original = real.read_text(encoding="utf-8")
    current = get_path(_yaml().load(original), dotted)
    if expect_from is not _MISSING and current != expect_from:
        raise ValueError(f"{dotted} is now {current!r}, not {expect_from!r}; run `careeros advise` again")
    old = set_path(real, dotted, value)
    try:
        validate(real)
    except BaseException:
        _write_atomic(real, original)
        raise
    return old
