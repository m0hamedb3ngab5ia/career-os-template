"""settings_io pure helpers: loader error -> field mapping, effective values, change grouping."""
from __future__ import annotations

import pytest

from careeros.ui.services import settings_io
from careeros.ui.settings_schema import get_section

pytestmark = pytest.mark.unit


def test_loader_error_maps_to_the_longest_matching_field_in_the_same_file():
    sec = get_section("runs")
    fid = settings_io.field_for_error(sec, "config/pipeline.yaml: runs.job_timeout_minutes.score must be a number > 0")
    assert fid == "pipeline:runs.job_timeout_minutes.score"
    assert settings_io.field_for_error(sec, "config/pipeline.yaml: schedule.jobs.scout needs exactly one of") == \
        "pipeline:schedule.jobs.scout"
    assert settings_io.field_for_error(sec, "config/targets.yaml: runs.preset is odd") is None
    assert settings_io.field_for_error(sec, "config/pipeline.yaml: something unrelated") is None


def test_loader_error_without_the_config_prefix_still_maps():
    sec = get_section("storage")
    msg = "pipeline.yaml: retention.run_summaries_days must be >= run_logs_days"
    assert settings_io.field_for_error(sec, msg) == "pipeline:retention.run_summaries_days"


def test_effective_values_fill_defaults():
    sec = get_section("runs")
    vals = settings_io.effective_values(sec, {"pipeline": {"runs": {"preset": "large"}}})
    assert vals["pipeline:runs.preset"] == "large"
    assert vals["pipeline:runs.ranking.freshness_weight"] == 60
    assert vals["pipeline:schedule.quiet_hours"] == {"start": "09:00", "end": "18:00"}


def test_explicit_null_is_a_value_not_a_missing_key():
    sec = get_section("runs")
    vals = settings_io.effective_values(sec, {"pipeline": {"schedule": {"quiet_hours": None}}})
    assert vals["pipeline:schedule.quiet_hours"] is None


def test_changes_grouped_by_file():
    sec = get_section("autonomy")
    by = settings_io.changes_by_file(sec, {"targets:volume.max_applications_per_day": 9,
                                           "pipeline:outreach.manual_if_mutuals": False})
    assert by == {"targets": [("volume.max_applications_per_day", 9)],
                  "pipeline": [("outreach.manual_if_mutuals", False)]}
