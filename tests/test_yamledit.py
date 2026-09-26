"""Multi-key, comment-preserving YAML writes (runs/yamledit.py) behind the UI's Settings forms and `advise apply`."""
from __future__ import annotations

import pytest

from careeros.config import ConfigError
from careeros.runs import yamledit

pytestmark = pytest.mark.unit

YAML = """# top comment
runs:
  preset: medium                 # small | medium (Recommended)
  job_timeout_minutes: {score: 10, prepare: 45}
  auto_submit:
    allow: [tier_c, tier_b]      # rules
    manual: [tier_a]
llm:
  allowed_tools:                 # passed as --allowedTools
    - Read                       # read files
    - Write                      # write files
    - Grep
safety:
  levels: {}                     # {CODE: level}
schedule:
  quiet_hours: {start: "09:00", end: "18:00"}  # quiet
"""


def _write(tmp_path, text=YAML):
    p = tmp_path / "pipeline.yaml"
    p.write_text(text)
    return p


def test_apply_changes_sets_several_keys_in_one_write(tmp_path):
    p = _write(tmp_path)
    old = yamledit.apply_changes(p, [("runs.preset", "small"), ("runs.job_timeout_minutes.score", 15)],
                                 validate=lambda path: None)
    assert old == {"runs.preset": "medium", "runs.job_timeout_minutes.score": 10}
    text = p.read_text()
    assert "preset: small                  # small | medium (Recommended)" in text
    assert "{score: 15, prepare: 45}" in text
    assert "# top comment" in text and text.count("\n") == YAML.count("\n")


def test_apply_changes_rolls_every_key_back_when_validation_fails(tmp_path):
    p = _write(tmp_path)

    def validate(path):
        raise ConfigError("nope")

    with pytest.raises(ConfigError):
        yamledit.apply_changes(p, [("runs.preset", "small"), ("runs.job_timeout_minutes.score", 15)],
                               validate=validate)
    assert p.read_text() == YAML


def test_flow_lists_and_maps_stay_flow(tmp_path):
    p = _write(tmp_path)
    yamledit.apply_changes(p, [("runs.auto_submit.allow", ["tier_c"]),
                               ("safety.levels", {"GHOST_OLD_POST": "off"})], validate=lambda path: None)
    text = p.read_text()
    assert "allow: [tier_c]" in text and "# rules" in text
    assert "levels: {GHOST_OLD_POST: off}" in text and "# {CODE: level}" in text


def test_block_list_keeps_comments_of_items_that_stay(tmp_path):
    p = _write(tmp_path)
    yamledit.apply_changes(p, [("llm.allowed_tools", ["Read", "Grep", "WebFetch"])], validate=lambda path: None)
    text = p.read_text()
    assert "- Read                       # read files" in text
    assert "Write" not in text and "# write files" not in text
    assert "- WebFetch" in text
    assert "# passed as --allowedTools" in text


def test_unchanged_value_leaves_the_file_byte_identical(tmp_path):
    p = _write(tmp_path)
    yamledit.apply_changes(p, [("llm.allowed_tools", ["Read", "Write", "Grep"]),
                               ("runs.auto_submit.allow", ["tier_c", "tier_b"])], validate=lambda path: None)
    assert p.read_text() == YAML


def test_null_replaces_a_mapping(tmp_path):
    p = _write(tmp_path)
    yamledit.apply_changes(p, [("schedule.quiet_hours", None)], validate=lambda path: None)
    assert "quiet_hours: null" in p.read_text()


def test_preview_changes_returns_a_diff_and_writes_nothing(tmp_path):
    p = _write(tmp_path)
    diff = yamledit.preview_changes(p, [("runs.preset", "large")])
    assert "-  preset: medium" in diff and "+  preset: large" in diff
    assert p.read_text() == YAML


def test_preview_of_no_change_is_empty(tmp_path):
    p = _write(tmp_path)
    assert yamledit.preview_changes(p, [("runs.preset", "medium")]) == ""


def test_apply_changes_many_rolls_back_every_file(tmp_path):
    a = _write(tmp_path)
    b = tmp_path / "targets.yaml"
    b.write_text("volume:\n  max_applications_per_day: 15   # cap\n")

    def validate(paths):
        assert set(paths) == {a.resolve(), b.resolve()}
        raise ConfigError("bad")

    with pytest.raises(ConfigError):
        yamledit.apply_changes_many({a: [("runs.preset", "small")], b: [("volume.max_applications_per_day", 3)]},
                                    validate=validate)
    assert a.read_text() == YAML and "15   # cap" in b.read_text()
    yamledit.apply_changes_many({a: [("runs.preset", "small")], b: [("volume.max_applications_per_day", 3)]},
                                validate=lambda paths: None)
    assert "preset: small" in a.read_text() and "max_applications_per_day: 3    # cap" in b.read_text()


def test_apply_changes_writes_through_a_symlink(tmp_path):
    real = tmp_path / "private" / "pipeline.yaml"
    real.parent.mkdir()
    real.write_text(YAML)
    link = tmp_path / "config" / "pipeline.yaml"
    link.parent.mkdir()
    link.symlink_to(real)
    yamledit.apply_changes(link, [("runs.preset", "large")], validate=lambda path: None)
    assert link.is_symlink() and "preset: large" in real.read_text()


def test_nested_new_mapping_is_created(tmp_path):
    p = _write(tmp_path)
    yamledit.apply_changes(p, [("runs.retry.max_attempts", 3)], validate=lambda path: None)
    assert "max_attempts: 3" in p.read_text()
