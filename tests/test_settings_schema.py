"""The declarative Settings schema (src/careeros/ui/settings_schema): shape, coverage of every example config key,
defaults in step with examples/config, and per-control validation."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ruamel.yaml import YAML

from careeros.ui.settings_schema import (CONTROLS, NOT_IN_UI, SECTIONS, Field, Policy, get_section, reset_group,
                                         validate_value)

pytestmark = pytest.mark.unit

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "config"
EXPECTED_SECTIONS = ("general", "targets", "autonomy", "safety", "scout", "companies", "outreach", "notifications",
                     "runs", "storage", "qa")


def _fields():
    for sec in SECTIONS:
        for f in sec.fields():
            yield sec, f


def _example(file: str):
    return yaml.safe_load((EXAMPLES / f"{file}.yaml").read_text())


def _get(data, dotted):
    cur = data
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return KeyError
        cur = cur[k]
    return cur


def _leaves(d, pre=""):
    for k, v in d.items():
        key = f"{pre}.{k}" if pre else str(k)
        if isinstance(v, dict) and v:
            yield from _leaves(v, key)
        else:
            yield key


def _covered(file: str, key: str) -> bool:
    for _, f in _fields():
        if f.file == file and (f.key == key or key.startswith(f.key + ".")):
            return True
    return any(file == nf and (key == nk or key.startswith(nk + ".")) for (nf, nk) in NOT_IN_UI)


# --- shape ------------------------------------------------------------------------------------------------

def test_sections_are_the_settings_nav_plus_quality_checks():
    assert tuple(s.id for s in SECTIONS) == EXPECTED_SECTIONS
    assert get_section("runs").title and get_section("nope") is None


def test_every_field_is_well_formed():
    for sec, f in _fields():
        assert f.control in CONTROLS, f.id
        assert f.label and f.label[0].isupper(), f.id
        assert f.file in ("targets", "companies", "qa", "pipeline"), f.id
        assert f.id == f"{f.file}:{f.key}"
        if f.control in ("select", "preset_cards"):
            assert f.options, f.id
    for sec in SECTIONS:
        ids = [f.id for f in sec.fields()]
        assert len(ids) == len(set(ids)), sec.id
        assert {g.id for g in sec.groups} and all(g.title for g in sec.groups)


def test_policy_rows_are_locked_and_cover_the_four_rules():
    policies = [p for s in SECTIONS for g in s.groups for p in g.items if isinstance(p, Policy)]
    text = " ".join(p.label + " " + p.value for p in policies).lower()
    for must in ("linkedin", "thank-you", "tier a", "never apply"):
        assert must in text, must
    tier_a = next(f for _, f in _fields() if f.key == "tiers.A.auto_submit")
    assert tier_a.locked and "never" in tier_a.note.lower()
    auto = next(f for _, f in _fields() if f.key == "runs.auto_submit.enabled")
    assert auto.readonly and "never apply" in auto.note.lower()


def test_to_dict_is_json_ready():
    import json

    for sec in SECTIONS:
        json.dumps(sec.to_dict())


# --- coverage and defaults vs examples/config -------------------------------------------------------------

@pytest.mark.parametrize("file", ["targets", "companies", "qa", "pipeline"])
def test_every_example_key_is_in_the_ui_or_explicitly_not(file):
    missing = [k for k in _leaves(_example(file)) if not _covered(file, k)]
    assert not missing, f"{file}.yaml keys with no schema field and no NOT_IN_UI entry: {missing}"


def test_not_in_ui_entries_have_reasons_and_exist():
    for (file, key), reason in NOT_IN_UI.items():
        assert len(reason) > 20, (file, key)
        if file == "categories":
            continue
        assert _get(_example(file), key) is not KeyError, (file, key)


def test_field_keys_exist_in_the_example_files():
    for _, f in _fields():
        assert _get(_example(f.file), f.key) is not KeyError, f.id


def test_defaults_match_the_example_files():
    for _, f in _fields():
        if f.personal:
            assert f.default is None and not f.recommended, f.id
            continue
        assert f.default == _get(_example(f.file), f.key), f.id


def test_recommended_markers_in_the_examples_are_recommended_fields():
    for file in ("targets", "pipeline", "qa", "companies"):
        text = (EXAMPLES / f"{file}.yaml").read_text().splitlines()
        doc = YAML(typ="rt").load("\n".join(text))

        def walk(node, pre=""):
            for k, v in node.items():
                key = f"{pre}.{k}" if pre else str(k)
                line = node.lc.key(k)[0]
                if "(Recommended)" in text[line]:
                    yield key
                if isinstance(v, dict):
                    yield from walk(v, key)

        for key in walk(doc):
            owners = [f for _, f in _fields() if f.file == file and (f.key == key or f.key.startswith(key + ".")
                                                                      or key.startswith(f.key + "."))]
            if not owners:
                assert any(file == nf and key.startswith(nk) for (nf, nk) in NOT_IN_UI), key
                continue
            assert any(o.recommended for o in owners), f"{file}:{key}"


# --- validation -------------------------------------------------------------------------------------------

def _f(key: str) -> Field:
    return next(f for _, f in _fields() if f.key == key)


@pytest.mark.parametrize("key,value,ok", [
    ("runs.max_consecutive_failures", 3, True),
    ("runs.max_consecutive_failures", 0, False),
    ("runs.max_consecutive_failures", 2.5, False),
    ("runs.max_consecutive_failures", True, False),
    ("runs.max_consecutive_failures", "3", False),
    ("runs.ranking.fit_weight", 0.75, True),
    ("runs.preset", "medium", True),
    ("runs.preset", "huge", False),
    ("runs.stop_on_timeout", False, True),
    ("runs.stop_on_timeout", "no", False),
    ("llm.allowed_tools", ["Read", "Bash(date *)"], True),
    ("llm.allowed_tools", ["Read", ""], False),
    ("llm.allowed_tools", "Read", False),
    ("schedule.quiet_hours", {"start": "22:00", "end": "07:00"}, True),
    ("schedule.quiet_hours", None, True),
    ("schedule.quiet_hours", {"start": "25:00", "end": "07:00"}, False),
    ("schedule.jobs.scout", {"every_hours": 2}, True),
    ("schedule.jobs.scout", {"every_hours": 2, "at": ["01:00"]}, False),
    ("schedule.jobs.score", {"at": ["01:00"], "preset": "small"}, True),
    ("runs.auto_submit.manual", ["tier_a", "fit_gte_90"], True),
    ("runs.auto_submit.manual", ["tier_z"], False),
    ("safety.levels", {"GHOST_OLD_POST": "off", "SCAM_FREE_EMAIL_RECRUITER": "block"}, True),
    ("safety.levels", {"GHOST_OLD_POST": "maybe"}, False),
    ("safety.levels", {"NOT_A_CODE": "off"}, False),
    ("tier_rules", [{"if": "fit >= 80", "tier": "B"}], True),
    ("tier_rules", [{"if": "fit >= 80", "tier": "D"}], False),
    ("volume.season_multiplier", {"9": 2.0, "1": 1.5}, True),
    ("volume.season_multiplier", {"13": 2.0}, False),
    ("candidate.graduation", "2026-05", True),
    ("candidate.graduation", "May 2026", False),
    ("candidate.current_base_usd", None, True),
    ("tiers.B.cover_letter", "if_required", True),
    ("tiers.B.cover_letter", "sometimes", False),
    ("tiers.B.review_required", ["resume", "form"], True),
    ("tiers.B.review_required", ["essay"], False),
    ("scout.sources", ["greenhouse"], True),
    ("scout.sources", ["monster"], False),
    ("boards", [{"company": "Acme", "ats": "greenhouse", "slug": "acme"}], True),
    ("boards", [{"company": "Acme", "ats": "greenhouse"}], False),
    ("company_domains", {"Acme": "acme.com", "Beta": ["beta.io", "betajobs.com"]}, True),
    ("company_domains", {"Acme": 3}, False),
    ("advisor.failure_rate_warn", 1.5, False),
])
def test_validate_value(key, value, ok):
    err = validate_value(_f(key), value)
    assert (err is None) == ok, err


def test_errors_are_plain_language():
    assert "whole number" in validate_value(_f("runs.max_consecutive_failures"), 2.5)
    assert "at least 1" in validate_value(_f("runs.max_consecutive_failures"), 0)


def test_section_checks_catch_cross_field_mistakes():
    safety = get_section("safety")
    errs = safety.check({"targets:safety.ghost.old_post_days": 30, "targets:safety.ghost.very_old_post_days": 30})
    assert errs and errs[0][0] == "targets:safety.ghost.very_old_post_days" and "31" in errs[0][1]
    qa = get_section("qa")
    assert qa.check({"qa:cover_letter.min_words": 300, "qa:cover_letter.max_words": 250})


def test_reset_group_gives_recommended_values_for_editable_fields_only():
    ch = reset_group("runs", "ranking")
    assert ch["pipeline:runs.ranking.freshness_weight"] == 60 and len(ch) == 8
    assert "pipeline:runs.auto_submit.enabled" not in reset_group("runs", "auto_submit")
    assert reset_group("targets", "candidate") == {}
    with pytest.raises(KeyError):
        reset_group("runs", "nope")


def test_safety_codes_match_the_checks_in_the_source():
    import re

    from careeros.ui.settings_schema import SAFETY_CODES

    src = Path(__file__).resolve().parents[1] / "src" / "careeros" / "safety"
    found = set()
    for f in src.glob("*.py"):
        found |= set(re.findall(r'"((?:SCAM|GHOST|COMPANY|FIELD)_[A-Z_]+)"', f.read_text()))
    assert set(SAFETY_CODES) == found
