"""careeros.ui.openapi: the schema dump is stable and machine-independent, and carries the typed routes."""
from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")

from careeros.ui.openapi import dump  # noqa: E402

pytestmark = pytest.mark.unit


def test_dump_is_deterministic_sorted_and_has_no_local_paths(tmp_path):
    out = dump()
    assert out == dump() and out.endswith("\n")
    assert json.dumps(json.loads(out), indent=2, sort_keys=True, ensure_ascii=False) + "\n" == out
    assert "/nonexistent" not in out and "/Users/" not in out and "/home/" not in out


def test_meta_and_status_have_response_shapes():
    s = json.loads(dump())
    ok = lambda path: s["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]  # noqa: E731
    assert ok("/api/meta") == {"$ref": "#/components/schemas/Meta"}
    assert ok("/api/status") == {"$ref": "#/components/schemas/Status"}
    tiles = s["components"]["schemas"]["Tiles"]
    assert set(tiles["required"]) == {"applied_week", "needs_you", "interviews", "response_rate"}
