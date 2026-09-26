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
    assert "levels: {GHOST_OLD_POST: \"off\"}" in text and "# {CODE: level}" in text


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


# --- YAML 1.1 readers (PyYAML) must read back exactly what was written ------------------------------------

AMBIGUOUS = ["10:30", "22:00", "07:00", "11:15", "off", "on", "yes", "no", "Yes", "OFF", "y", "n", "true", "False",
             "null", "~", "", "12", "1.5", "1e3", "0x1F", "0o17", "017", "1_000", ".inf", "-.nan", "2026-05",
             "2026-05-01", "@x", "a: b", "# not a comment", "- dash", "[x]", "{x}", "*star", "&amp", "!tag", "%p",
             "`tick", "'q'", '"dq"', "trailing ", " leading", "a  b"]


@pytest.mark.parametrize("value", AMBIGUOUS)
def test_every_string_reads_back_as_the_same_string(tmp_path, value):
    import yaml

    p = _write(tmp_path)
    yamledit.apply_changes(p, [("runs.preset", value), ("llm.allowed_tools", ["Read", value]),
                               ("safety.levels", {"GHOST_OLD_POST": value}),
                               ("runs.auto_submit.allow", [value])], validate=lambda path: None)
    data = yaml.safe_load(p.read_text())
    assert data["runs"]["preset"] == value
    assert data["llm"]["allowed_tools"] == ["Read", value]
    assert data["safety"]["levels"] == {"GHOST_OLD_POST": value}
    assert data["runs"]["auto_submit"]["allow"] == [value]


def test_string_keys_that_look_like_numbers_stay_strings(tmp_path):
    import yaml

    p = tmp_path / "t.yaml"
    p.write_text('volume:\n  season_multiplier:\n    "9": 2.0\n')
    yamledit.apply_changes(p, [("volume.season_multiplier", {"9": 2.0, "10": 1.5})], validate=lambda path: None)
    assert yaml.safe_load(p.read_text())["volume"]["season_multiplier"] == {"9": 2.0, "10": 1.5}


def test_an_existing_quote_style_is_kept(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text("a: 'x'   # c\nb: \"y\"\n")
    yamledit.apply_changes(p, [("a", "z"), ("b", "y")], validate=lambda path: None)
    assert p.read_text() == "a: 'z'   # c\nb: \"y\"\n"


# --- partial failures leave every file as it was ----------------------------------------------------------

def test_a_write_failing_on_the_second_file_restores_the_first(tmp_path, monkeypatch):
    a = _write(tmp_path)
    b = tmp_path / "targets.yaml"
    b.write_text("volume:\n  max_applications_per_day: 15   # cap\n")
    before_a, before_b = a.read_text(), b.read_text()
    real = yamledit._write_atomic
    calls = []

    def flaky(path, text):
        calls.append(path)
        if path == b.resolve() and len([c for c in calls if c == b.resolve()]) == 1:
            raise OSError("disk full")
        real(path, text)

    monkeypatch.setattr(yamledit, "_write_atomic", flaky)
    with pytest.raises(OSError):
        yamledit.apply_changes_many({a: [("runs.preset", "small")], b: [("volume.max_applications_per_day", 3)]},
                                    validate=lambda paths: None)
    assert a.read_text() == before_a and b.read_text() == before_b
    assert not list(tmp_path.glob(".*.tmp"))


def test_a_failed_replace_leaves_no_temp_file(tmp_path, monkeypatch):
    import os

    a = _write(tmp_path)

    def boom(src, dst):
        raise OSError("read-only")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        yamledit.apply_changes(a, [("runs.preset", "small")], validate=lambda path: None)
    assert a.read_text() == YAML and not list(tmp_path.glob(".*.tmp"))


def test_a_bad_key_path_on_the_second_file_writes_nothing(tmp_path):
    a = _write(tmp_path)
    b = tmp_path / "companies.yaml"
    b.write_text("boards:\n  - {company: Acme, ats: greenhouse, slug: acme}\n")
    before_b = b.read_text()
    with pytest.raises(ValueError, match="boards"):
        yamledit.apply_changes_many({a: [("runs.preset", "small")], b: [("boards.slug", "x")]},
                                    validate=lambda paths: None)
    assert a.read_text() == YAML and b.read_text() == before_b


# --- keep_layout must not swallow whitespace-only edits ----------------------------------------------------

def test_an_edit_that_only_changes_inner_whitespace_is_written(tmp_path):
    import yaml

    p = tmp_path / "t.yaml"
    p.write_text("tiers:\n  A:\n    description: dream firms   # note\nweak:\n  - worked on\n  - helped\n")
    yamledit.apply_changes(p, [("tiers.A.description", "dream  firms"), ("weak", ["worked  on", "helped"])],
                           validate=lambda path: None)
    data = yaml.safe_load(p.read_text())
    assert data["tiers"]["A"]["description"] == "dream  firms"
    assert data["weak"] == ["worked  on", "helped"]
    assert "# note" in p.read_text()


def test_aligned_flow_mappings_keep_their_spacing(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text("presets:\n  small:  {a: 1}\n  medium: {a: 2}\npreset: small\n")
    yamledit.apply_changes(p, [("preset", "medium")], validate=lambda path: None)
    assert p.read_text() == "presets:\n  small:  {a: 1}\n  medium: {a: 2}\npreset: medium\n"


def test_saving_the_same_string_over_an_unquoted_ambiguous_one_rewrites_it_quoted(tmp_path):
    import yaml

    p = tmp_path / "t.yaml"
    p.write_text("levels: {GHOST_OLD_POST: off}   # c\nat: [10:30]\nname: plain\n")
    yamledit.apply_changes(p, [("levels", {"GHOST_OLD_POST": "off"}), ("at", ["10:30"]), ("name", "plain")],
                           validate=lambda path: None)
    assert yaml.safe_load(p.read_text()) == {"levels": {"GHOST_OLD_POST": "off"}, "at": ["10:30"], "name": "plain"}
    assert "# c" in p.read_text() and "name: plain\n" in p.read_text()


def test_examples_read_the_same_in_yaml_1_1_and_1_2():
    """The shipped config must mean the same to PyYAML (the CLI) and ruamel (the writer)."""
    import json
    from pathlib import Path

    import yaml

    for f in (Path(__file__).resolve().parents[1] / "examples" / "config").glob("*.yaml"):
        text = f.read_text()
        a = json.loads(json.dumps(yaml.safe_load(text), default=str))
        b = json.loads(json.dumps(yamledit._yaml().load(text), default=str))
        assert a == b, f.name
