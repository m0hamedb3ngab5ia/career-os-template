"""ui_state router functions (REQ-121): missing/broken/invalid file -> defaults; put writes the file."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
from careeros.ui.routers.ui_state import UiState, get_ui_state, put_ui_state  # noqa: E402

pytestmark = pytest.mark.unit


def _ctx(tmp_path):
    return SimpleNamespace(settings=SimpleNamespace(root=tmp_path))


def _write(tmp_path, text):
    p = tmp_path / "data" / "ui_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_missing_file_is_default(tmp_path):
    assert get_ui_state(_ctx(tmp_path)).tour_done is False


def test_broken_json_is_default(tmp_path):
    _write(tmp_path, "{not json")
    assert get_ui_state(_ctx(tmp_path)).tour_done is False


def test_wrong_type_is_default(tmp_path):
    _write(tmp_path, json.dumps({"tour_done": "yes"}))
    assert get_ui_state(_ctx(tmp_path)).tour_done is False


def test_put_writes_file(tmp_path):
    assert put_ui_state(UiState(tour_done=True), _ctx(tmp_path)).tour_done is True
    assert json.loads((tmp_path / "data" / "ui_state.json").read_text()) == {"tour_done": True}
    assert get_ui_state(_ctx(tmp_path)).tour_done is True
