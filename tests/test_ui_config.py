"""`pipeline.yaml: ui` (careeros ui): defaults, validation, the example file in step with the code."""
from __future__ import annotations

import copy

import pytest
import yaml
from conftest import EXAMPLE_REPO

from careeros.config import ConfigError
from careeros.models import STATUSES
from careeros.ui.config import DEFAULT_COLUMNS, UiConfig, load_ui_config

pytestmark = pytest.mark.unit


class S:
    def __init__(self, pipeline):
        self.pipeline = pipeline


def example_pipeline() -> dict:
    return yaml.safe_load((EXAMPLE_REPO / "config" / "pipeline.yaml").read_text())


def test_defaults_without_ui_block():
    cfg = load_ui_config(S({}))
    assert cfg == UiConfig()
    assert (cfg.port, cfg.host, cfg.open_browser, cfg.theme) == (8765, "127.0.0.1", True, "system")
    assert (cfg.undo_seconds, cfg.page_size, cfg.watch_debounce_ms) == (8, 100, 300)
    assert [c["name"] for c in cfg.columns] == ["Found", "Queued", "Needs review", "Applied",
                                                "Screening · Interview", "Offer"]


def test_default_columns_leave_the_closed_statuses_for_the_summary():
    cfg = load_ui_config(S({}))
    in_columns = {s for c in cfg.columns for s in c["statuses"]}
    assert set(cfg.closed) == set(STATUSES) - in_columns
    assert {"rejected", "withdrawn", "ghosted", "skipped"} <= set(cfg.closed)


def test_example_config_matches_code_defaults():
    assert load_ui_config(S(example_pipeline())) == load_ui_config(S({}))


def test_example_file_marks_recommended_defaults():
    text = (EXAMPLE_REPO / "config" / "pipeline.yaml").read_text()
    ui = text[text.index("\nui:"):]
    assert ui.count("(Recommended)") >= 6


def test_overrides_and_custom_columns():
    cfg = load_ui_config(S({"ui": {"port": 9000, "theme": "dark", "pipeline": {"columns": [
        {"name": "New", "statuses": ["found"]}, {"name": "Doing", "statuses": ["queued", "prepared"]}]}}}))
    assert cfg.port == 9000 and cfg.theme == "dark"
    assert [c["name"] for c in cfg.columns] == ["New", "Doing"]
    assert "scored" in cfg.closed and "found" not in cfg.closed


@pytest.mark.parametrize("bad", [
    {"ui": []},
    {"ui": {"nope": 1}},
    {"ui": {"port": 0}},
    {"ui": {"port": 70000}},
    {"ui": {"port": "8765"}},
    {"ui": {"host": ""}},
    {"ui": {"open_browser": "yes"}},
    {"ui": {"theme": "blue"}},
    {"ui": {"undo_seconds": 0}},
    {"ui": {"page_size": 5}},
    {"ui": {"watch_debounce_ms": 10}},
    {"ui": {"pipeline": {"columns": []}}},
    {"ui": {"pipeline": {"columns": [{"name": "X", "statuses": ["nope"]}]}}},
    {"ui": {"pipeline": {"columns": [{"name": "", "statuses": ["found"]}]}}},
    {"ui": {"pipeline": {"columns": [{"name": "A", "statuses": ["found"]}, {"name": "B", "statuses": ["found"]}]}}},
    {"ui": {"pipeline": {"columns": [{"name": "A", "statuses": ["found"], "x": 1}]}}},
    {"ui": {"pipeline": {"nope": 1}}},
])
def test_invalid_config_fails_closed(bad):
    with pytest.raises(ConfigError):
        load_ui_config(S(bad))


def test_default_columns_are_not_shared_state():
    cfg = load_ui_config(S({}))
    cfg.columns[0]["statuses"].append("x")
    assert "x" not in DEFAULT_COLUMNS[0]["statuses"]
    assert load_ui_config(S(copy.deepcopy({}))).columns[0]["statuses"] == DEFAULT_COLUMNS[0]["statuses"]
