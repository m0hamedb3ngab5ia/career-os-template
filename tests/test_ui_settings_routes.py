"""Unit tests for the Settings page helpers behind the routes: the 422 body, relative file paths, the draft-weight
check of the ranking preview and the section list."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from careeros.ui.services import settings_page as svc
from careeros.ui.services.settings_io import SettingsInvalid

pytestmark = pytest.mark.unit


def test_invalid_body_counts_errors():
    e = SettingsInvalid({"a:x": "Must be at least 1.", "a:y": "Enter a number."}, ["general one"])
    body = svc.invalid_body(e)
    assert body["fields"] == {"a:x": "Must be at least 1.", "a:y": "Enter a number."}
    assert body["general"] == ["general one"]
    assert body["detail"] == "Fix 3 errors to save."
    assert svc.invalid_body(SettingsInvalid({"a:x": "bad"}))["detail"] == "Fix 1 error to save."


def test_relative_files_hide_the_absolute_root(tmp_path: Path):
    files = {"pipeline": str(tmp_path / "config" / "pipeline.yaml"), "other": "/elsewhere/x.yaml"}
    assert svc.relative_files(files, tmp_path) == {"pipeline": "config/pipeline.yaml", "other": "x.yaml"}


def test_section_list_is_schema_order_with_files():
    ids = [s["id"] for s in svc.section_list()]
    assert ids[0] == "general" and ids.index("runs") < ids.index("storage")
    assert all({"id", "title", "help", "files"} <= set(s) for s in svc.section_list())


@pytest.mark.parametrize("weights, msg", [
    ({"nope": 1}, "unknown ranking weight"),
    ({"freshness_weight": -1}, "0 or more"),
    ({"freshness_weight": True}, "0 or more"),
    ({"freshness_weight": "a"}, "0 or more"),
])
def test_check_weights_refuses_bad_input(weights, msg):
    with pytest.raises(ValueError, match=msg):
        svc.check_weights(weights)


def test_check_weights_accepts_known_numbers():
    assert svc.check_weights({"freshness_weight": 10, "fit_weight": 0.5}) == {"freshness_weight": 10.0,
                                                                              "fit_weight": 0.5}


def test_ranking_preview_refuses_unknown_kind():
    with pytest.raises(ValueError, match="score or prepare"):
        svc.ranking_preview(None, "apply", {}, datetime.now(timezone.utc))  # type: ignore[arg-type]
