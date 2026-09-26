"""Settings forms end to end on a temp root built from examples/config: read, diff, save (comments kept, only the
changed lines differ), per-field errors, loader rollback, multi-file sections and a symlinked config/."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from conftest import EXAMPLE_REPO, make_temp_root

from careeros.config import ConfigError, Settings
from careeros.ui.services import settings_io
from careeros.ui.services.settings_io import SettingsConflict, SettingsInvalid

pytestmark = pytest.mark.integration


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = make_temp_root(tmp_path / "repo")
    # make_temp_root rewrites pipeline.yaml without comments; put the commented example back
    shutil.copy(EXAMPLE_REPO / "config" / "pipeline.yaml", r / "config" / "pipeline.yaml")
    return r


def _s(root: Path) -> Settings:
    return Settings.load(root)


def _changed_lines(before: str, after: str) -> list[tuple[str, str]]:
    b, a = before.splitlines(), after.splitlines()
    assert len(b) == len(a)
    return [(x, y) for x, y in zip(b, a) if x != y]


def test_read_section_gives_schema_values_defaults_and_files(root):
    out = settings_io.read_section(_s(root), "runs")
    assert out["section"]["id"] == "runs" and out["section"]["groups"]
    assert out["values"]["pipeline:runs.preset"] == "medium"
    assert out["defaults"]["pipeline:runs.preset"] == "medium"
    assert out["files"] == {"pipeline": str(root / "config" / "pipeline.yaml")}
    assert out["version"]


def test_missing_keys_read_as_their_defaults(root):
    p = root / "config" / "pipeline.yaml"
    text = p.read_text()
    start = text.index("  ranking:")
    end = text.index("  required_mcp_servers:")
    p.write_text(text[:start] + text[end:])
    out = settings_io.read_section(_s(root), "runs")
    assert out["values"]["pipeline:runs.ranking.freshness_weight"] == 60


def test_diff_shows_the_change_and_writes_nothing(root):
    p = root / "config" / "pipeline.yaml"
    before = p.read_text()
    out = settings_io.diff_section(_s(root), "runs", {"pipeline:runs.preset": "large"})
    assert "+  preset: large" in out["diffs"]["pipeline"] and p.read_text() == before


def test_save_keeps_comments_and_changes_only_the_edited_lines(root):
    p = root / "config" / "pipeline.yaml"
    before = p.read_text()
    res = settings_io.save_section(_s(root), "runs", {"pipeline:runs.preset": "small",
                                                      "pipeline:runs.max_consecutive_failures": 5})
    assert res["old"] == {"pipeline:runs.preset": "medium", "pipeline:runs.max_consecutive_failures": 3}
    changed = _changed_lines(before, p.read_text())
    assert [a.split("#")[0].strip() for _, a in changed] == ["preset: small", "max_consecutive_failures: 5"]
    assert all("#" in a for _, a in changed), "end-of-line comments kept"
    assert settings_io.read_section(_s(root), "runs")["values"]["pipeline:runs.preset"] == "small"


def test_field_errors_block_the_save(root):
    p = root / "config" / "pipeline.yaml"
    before = p.read_text()
    with pytest.raises(SettingsInvalid) as e:
        settings_io.save_section(_s(root), "runs", {"pipeline:runs.max_consecutive_failures": 0,
                                                    "pipeline:runs.preset": "huge",
                                                    "pipeline:runs.stop_on_timeout": False})
    assert set(e.value.fields) == {"pipeline:runs.max_consecutive_failures", "pipeline:runs.preset"}
    assert p.read_text() == before


def test_unknown_locked_and_readonly_fields_are_refused(root):
    with pytest.raises(SettingsInvalid) as e:
        settings_io.save_section(_s(root), "runs", {"pipeline:runs.auto_submit.enabled": True,
                                                    "pipeline:nope": 1})
    assert "can't be changed" in e.value.fields["pipeline:runs.auto_submit.enabled"]
    assert "pipeline:nope" in e.value.fields
    with pytest.raises(SettingsInvalid):
        settings_io.save_section(_s(root), "autonomy", {"targets:tiers.A.auto_submit": True})


def test_cross_field_check_names_the_field(root):
    with pytest.raises(SettingsInvalid) as e:
        settings_io.save_section(_s(root), "safety", {"targets:safety.ghost.very_old_post_days": 20})
    assert "Old post" in e.value.fields["targets:safety.ghost.very_old_post_days"]


def test_a_loader_failure_rolls_back_and_maps_to_the_field(root):
    p = root / "config" / "pipeline.yaml"
    before = p.read_text()
    with pytest.raises(SettingsInvalid) as e:
        settings_io.save_section(_s(root), "storage", {"pipeline:retention.run_summaries_days": 10})
    assert "run_summaries_days" in e.value.fields["pipeline:retention.run_summaries_days"]
    assert p.read_text() == before


def test_a_loader_error_with_no_field_is_general(root, monkeypatch):
    p = root / "config" / "pipeline.yaml"
    before = p.read_text()

    def boom(root_path):
        raise ConfigError("config/pipeline.yaml: something else broke")

    monkeypatch.setattr(settings_io, "validate_root", boom)
    with pytest.raises(SettingsInvalid) as e:
        settings_io.save_section(_s(root), "runs", {"pipeline:runs.preset": "small"})
    assert e.value.general and not e.value.fields and p.read_text() == before


def test_multi_file_section_rolls_back_both_files(root, monkeypatch):
    t, p = root / "config" / "targets.yaml", root / "config" / "pipeline.yaml"
    tb, pb = t.read_text(), p.read_text()

    def boom(root_path):
        raise ConfigError("config/targets.yaml: volume.max_applications_per_day must be a whole number")

    monkeypatch.setattr(settings_io, "validate_root", boom)
    with pytest.raises(SettingsInvalid) as e:
        settings_io.save_section(_s(root), "autonomy", {"targets:volume.max_applications_per_day": 9,
                                                        "pipeline:outreach.manual_if_mutuals": False})
    assert "targets:volume.max_applications_per_day" in e.value.fields
    assert t.read_text() == tb and p.read_text() == pb
    monkeypatch.undo()
    settings_io.save_section(_s(root), "autonomy", {"targets:volume.max_applications_per_day": 9,
                                                    "pipeline:outreach.manual_if_mutuals": False})
    assert "max_applications_per_day: 9" in t.read_text() and "manual_if_mutuals: false" in p.read_text()


def test_writes_go_through_a_symlinked_config(root, tmp_path):
    private = tmp_path / "private" / "config"
    shutil.move(str(root / "config"), str(private))
    (root / "config").mkdir()
    for f in private.iterdir():
        (root / "config" / f.name).symlink_to(f)
    settings_io.save_section(_s(root), "notifications", {"pipeline:notify.daily_digest": False})
    assert (root / "config" / "pipeline.yaml").is_symlink()
    assert "daily_digest: false" in (private / "pipeline.yaml").read_text()


def test_a_stale_version_is_refused(root):
    v = settings_io.read_section(_s(root), "runs")["version"]
    settings_io.save_section(_s(root), "runs", {"pipeline:runs.preset": "small"}, version=v)
    with pytest.raises(SettingsConflict):
        settings_io.save_section(_s(root), "runs", {"pipeline:runs.preset": "large"}, version=v)


def test_lists_and_schedule_blocks_round_trip(root):
    p = root / "config" / "pipeline.yaml"
    settings_io.save_section(_s(root), "runs", {
        "pipeline:llm.allowed_tools": ["Read", "Write", "Edit", "Glob", "Grep", "Bash(.venv/bin/careeros *)"],
        "pipeline:schedule.jobs.scout": {"every_hours": 2},
        "pipeline:schedule.quiet_hours": None,
        "pipeline:runs.auto_submit.manual": ["tier_a", "fit_gte_90"],
    })
    text = p.read_text()
    assert "scout: {every_hours: 2}" in " ".join(text.split()) and "quiet_hours: null" in text
    assert "manual: [tier_a, fit_gte_90]" in text and "WebFetch" not in text
    assert "# prepare-job use. A tool a skill needs" in text
    vals = settings_io.read_section(_s(root), "runs")["values"]
    assert vals["pipeline:schedule.jobs.scout"] == {"every_hours": 2} and vals["pipeline:schedule.quiet_hours"] is None


def test_reset_group_then_save_restores_recommended(root):
    settings_io.save_section(_s(root), "runs", {"pipeline:runs.ranking.freshness_weight": 10})
    changes = settings_io.reset_changes("runs", "ranking")
    settings_io.save_section(_s(root), "runs", changes)
    assert settings_io.read_section(_s(root), "runs")["values"]["pipeline:runs.ranking.freshness_weight"] == 60


def test_unknown_section():
    with pytest.raises(KeyError):
        settings_io.read_section(None, "nope")  # type: ignore[arg-type]
