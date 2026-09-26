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
    settings_io.save_section(_s(root), "outreach", {"pipeline:outreach.manual_if_mutuals": False})
    assert (root / "config" / "pipeline.yaml").is_symlink()
    assert "manual_if_mutuals: false" in (private / "pipeline.yaml").read_text()


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


# --- values the CLI's PyYAML loaders would misread if written unquoted -----------------------------------

def test_quiet_hours_after_ten_load_as_times(root):
    from datetime import time

    from careeros.runs.schedule import load_schedule

    settings_io.save_section(_s(root), "runs", {"pipeline:schedule.quiet_hours": {"start": "22:00", "end": "07:00"}})
    cfg = load_schedule(_s(root))
    assert (cfg.quiet_start, cfg.quiet_end) == (time(22, 0), time(7, 0))


def test_a_schedule_time_after_ten_round_trips(root):
    from datetime import time

    from careeros.runs.schedule import load_schedule

    settings_io.save_section(_s(root), "runs", {"pipeline:schedule.jobs.score": {"at": ["11:15"]}})
    assert load_schedule(_s(root)).jobs["score"].at == [time(11, 15)]
    assert settings_io.read_section(_s(root), "runs")["values"]["pipeline:schedule.jobs.score"] == {"at": ["11:15"]}


def test_level_off_turns_the_check_off(root):
    from careeros.safety.scam import Flag, apply_levels

    settings_io.save_section(_s(root), "safety", {"targets:safety.levels": {"GHOST_OLD_POST": "off"}})
    flags = [Flag("GHOST_OLD_POST", "info", "old"), Flag("SCAM_NO_INTERVIEW", "review", "x")]
    assert [f.code for f in apply_levels(flags, _s(root))] == ["SCAM_NO_INTERVIEW"]


def test_reset_schedule_to_recommended_saves(root):
    settings_io.save_section(_s(root), "runs", {"pipeline:schedule.jobs.score": {"at": ["11:15"]}})
    settings_io.save_section(_s(root), "runs", settings_io.reset_changes("runs", "schedule"))
    settings_io.save_section(_s(root), "runs", settings_io.reset_changes("runs", "quiet"))
    vals = settings_io.read_section(_s(root), "runs")["values"]
    assert vals["pipeline:schedule.jobs.score"] == {"at": ["01:00"]}


def test_every_option_of_every_string_field_round_trips_through_the_loaders(root):
    """Property-style: each select option, tag option and reason level, saved into its field, reads back the
    same through PyYAML (the CLI's reader), whatever YAML 1.1 would make of it unquoted."""
    import yaml

    from careeros.ui.settings_schema import SECTIONS

    for sec in SECTIONS:
        for f in sec.fields():
            if not f.editable or f.control not in ("select", "tags", "reason_levels", "text"):
                continue
            if f.control == "select":
                samples = list(f.options)
            elif f.control == "tags":
                samples = [list(f.options)] if f.options else [["off", "10:30", "yes", "12"]]
            elif f.control == "reason_levels":
                samples = [{code: lvl} for code, lvl in zip(f.options, ("off", "block", "skip", "review", "info"))]
            else:
                samples = ["off", "10:30"] if not f.pattern else []
            for v in samples:
                try:
                    settings_io.save_section(_s(root), sec.id, {f.id: v})
                except settings_io.SettingsInvalid:
                    continue  # the loaders refuse this value for this key; that's a checked failure, not a misread
                data = yaml.safe_load(settings_io.config_path(_s(root), f.file).read_text())
                cur = data
                for k in f.key.split("."):
                    cur = cur[k]
                assert cur == v, (f.id, v, cur)


# --- files hand-written with unquoted YAML-1.1-ambiguous values ---------------------------------------------

def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text, old
    path.write_text(text.replace(old, new, 1))


def test_unquoted_off_level_reads_as_the_cli_applies_it_and_saving_repairs_it(root):
    from careeros.safety.scam import Flag, apply_levels

    t = root / "config" / "targets.yaml"
    _edit(t, "  levels: {}", "  levels: {GHOST_OLD_POST: off}")
    flags = [Flag("GHOST_OLD_POST", "info", "old")]
    assert [f.code for f in apply_levels(flags, _s(root))] == ["GHOST_OLD_POST"]  # the CLI keeps the check
    out = settings_io.read_section(_s(root), "safety")
    fid = "targets:safety.levels"
    assert out["values"][fid] == {}  # not off: the check runs at its built-in level, as the CLI does
    w = out["warnings"][fid]
    assert "off" in w["message"] and "quotes" in w["message"] and w["intended"] == {"GHOST_OLD_POST": "off"}
    settings_io.save_section(_s(root), "safety", {fid: w["intended"]})
    assert apply_levels(flags, _s(root)) == []
    after = settings_io.read_section(_s(root), "safety")
    assert after["values"][fid] == {"GHOST_OLD_POST": "off"} and fid not in after["warnings"]


def test_unquoted_yes_switch_reads_true_and_saving_writes_true(root):
    p = root / "config" / "pipeline.yaml"
    _edit(p, "  stop_on_timeout: true", "  stop_on_timeout: yes")
    out = settings_io.read_section(_s(root), "runs")
    fid = "pipeline:runs.stop_on_timeout"
    assert out["values"][fid] is True and out["warnings"][fid]["intended"] is True
    settings_io.save_section(_s(root), "runs", {fid: True})
    assert "stop_on_timeout: true" in p.read_text()
    assert fid not in settings_io.read_section(_s(root), "runs")["warnings"]


def test_unquoted_time_after_ten_is_flagged_and_saving_the_same_time_repairs_it(root):
    from datetime import time

    from careeros.runs.schedule import load_schedule

    p = root / "config" / "pipeline.yaml"
    _edit(p, 'score:   {at: ["01:00"]}', "score:   {at: [10:30]}")
    with pytest.raises(ConfigError):
        load_schedule(_s(root))  # PyYAML read 630
    out = settings_io.read_section(_s(root), "runs")
    fid = "pipeline:schedule.jobs.score"
    assert out["values"][fid] == {"at": [630]}
    assert out["warnings"][fid]["intended"] == {"at": ["10:30"]} and "10:30" in out["warnings"][fid]["message"]
    settings_io.save_section(_s(root), "runs", {fid: {"at": ["10:30"]}})
    assert load_schedule(_s(root)).jobs["score"].at == [time(10, 30)]
    assert fid not in settings_io.read_section(_s(root), "runs")["warnings"]


def test_the_shipped_examples_have_no_warnings(root):
    from careeros.ui.settings_schema import SECTIONS

    for sec in SECTIONS:
        assert settings_io.read_section(_s(root), sec.id)["warnings"] == {}, sec.id
