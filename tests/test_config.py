from __future__ import annotations

import warnings
from pathlib import Path

import pytest
import yaml

from careeros.config import ConfigError, Settings, SetupError, _fuzzy_eq, _load_yaml, find_repo_root, normalize_company

pytestmark = pytest.mark.unit


def _root(tmp_path: Path, pipeline: dict | None = None, companies: dict | None = None) -> Path:
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "profile").mkdir()
    (root / "config" / "pipeline.yaml").write_text(yaml.safe_dump(pipeline or {}))
    if companies is not None:
        (root / "config" / "companies.yaml").write_text(yaml.safe_dump(companies))
    return root


# --- path resolution -------------------------------------------------------

def test_paths_default_when_pipeline_has_none(tmp_path):
    root = _root(tmp_path)
    s = Settings.load(root)
    r = root.resolve()
    assert s.paths["jobs_dir"] == r / "data" / "jobs"
    assert s.paths["seen_file"] == r / "data" / "seen.json"
    assert s.paths["tracker_xlsx"] == r / "data" / "JobTracker.xlsx"  # gitignored data/, never outside the repo
    assert s.paths["profile"] == r / "profile" / "master.yaml"
    assert s.paths["standard_answers"] == r / "profile" / "standard_answers.yaml"
    assert s.profile == {} and s.standard_answers == {}


def test_paths_tilde_expanded_relative_resolved_absolute_kept(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    abs_seen = tmp_path / "elsewhere" / "seen.json"
    root = _root(tmp_path, {"paths": {
        "tracker_xlsx": "~/Documents/Jobs/JobTracker.xlsx",
        "jobs_dir": "data/../data/jobs",
        "seen_file": str(abs_seen),
        "output_dir_per_job": True,  # non-string values are ignored, not crashed on
    }})
    s = Settings.load(root)
    assert s.paths["tracker_xlsx"] == home / "Documents" / "Jobs" / "JobTracker.xlsx"
    assert "~" not in str(s.paths["tracker_xlsx"])
    assert s.paths["jobs_dir"] == root.resolve() / "data" / "jobs"
    assert s.paths["seen_file"] == abs_seen
    assert "output_dir_per_job" not in s.paths


def test_profile_path_override_is_loaded(tmp_path):
    root = _root(tmp_path, {"paths": {"profile": "me.yaml"}})
    (root / "me.yaml").write_text("identity: {name: Alex Example}\n")
    assert Settings.load(root).profile["identity"]["name"] == "Alex Example"


@pytest.mark.parametrize("missing", ["config", "profile"])
def test_load_without_personal_dirs_says_run_init(tmp_path, missing):
    root = _root(tmp_path)
    import shutil

    shutil.rmtree(root / missing)
    with pytest.raises(SetupError, match=r"careeros init") as exc:
        Settings.load(root)
    assert f"{missing}/" in str(exc.value)


def test_load_without_either_names_both(tmp_path):
    root = tmp_path / "bare"
    root.mkdir()
    with pytest.raises(SetupError, match=r"config/ and profile/ missing"):
        Settings.load(root)


def test_find_repo_root_accepts_fresh_checkout_with_only_examples(tmp_path, monkeypatch):
    monkeypatch.delenv("CAREEROS_ROOT", raising=False)
    root = tmp_path / "checkout"
    (root / "examples" / "config").mkdir(parents=True)
    (root / "examples" / "config" / "pipeline.yaml").write_text("paths: {}\n")
    (root / "src").mkdir()
    assert find_repo_root(root / "src") == root.resolve()


def test_find_repo_root_env_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREEROS_ROOT", str(tmp_path))
    assert find_repo_root(Path("/")) == tmp_path.resolve()


def test_find_repo_root_walks_up(tmp_path, monkeypatch):
    monkeypatch.delenv("CAREEROS_ROOT", raising=False)
    root = _root(tmp_path)
    deep = root / "a" / "b"
    deep.mkdir(parents=True)
    assert find_repo_root(deep) == root.resolve()


# --- yaml loading ----------------------------------------------------------

def test_load_yaml_missing_list_and_invalid(tmp_path):
    assert _load_yaml(tmp_path / "nope.yaml") == {}
    lst = tmp_path / "l.yaml"
    lst.write_text("- a\n- b\n")
    assert _load_yaml(lst) == {"_items": ["a", "b"]}
    empty = tmp_path / "e.yaml"
    empty.write_text("")
    assert _load_yaml(empty) == {}
    bad = tmp_path / "bad.yaml"
    bad.write_text("answers:\n  - key: x\n   answer: [unclosed\n")
    with pytest.raises(ConfigError, match=r"could not parse .*bad\.yaml"):  # fail closed, never silently {}
        _load_yaml(bad)


def test_settings_load_fails_closed_on_malformed_config(tmp_path):
    root = _root(tmp_path)
    (root / "config" / "targets.yaml").write_text("location:\n  blocked_countries: [DE\n")
    with pytest.raises(ConfigError, match="targets.yaml"):
        Settings.load(root)


# --- company normalization / matching ---------------------------------------

@pytest.mark.parametrize("raw,norm", [
    ("Stark Industries, Inc.", "stark industries"),
    ("AT&T", "at and t"),
    ("Initech LLC", "initech"),
    ("Hooli Holdings Corp.", "hooli"),
    ("  Pied   Piper  ", "pied piper"),
    ("Inc.", ""),
])
def test_normalize_company(raw, norm):
    assert normalize_company(raw) == norm


@pytest.mark.parametrize("a,b,eq", [
    ("initech", "initech", True),
    ("pied piper investments", "pied piper", True),  # multi-token prefix
    ("initech", "initech securities", False),         # single token never prefix-matches
    ("meta", "metabase", False),
    ("", "", False),
    ("pied pipers", "pied piper", False),
])
def test_fuzzy_eq(a, b, eq):
    assert _fuzzy_eq(a, b) is eq


def _s(companies: dict) -> Settings:
    return Settings(root=Path("."), companies=companies)


def test_prestige_tier_edges():
    s = _s({"prestige_tiers": {"sss": ["Initech"], "a": ["Pied Piper"], "avoid": ["Vandelay Consulting"], "empty": None},
            "prestige_scoring": {"bonus": {"sss": 10, "avoid": -100}}})
    assert s.prestige_tier("") is None
    assert s.prestige_tier("Inc.") is None
    assert s.prestige_tier("INITECH, INC.") == "sss"
    assert s.prestige_tier("Pied Piper Labs") == "a"
    assert s.prestige_tier("Initech Securities") is None  # single-token "initech" is not a prefix match
    assert s.prestige_bonus("Initech") == 10
    assert s.prestige_bonus("Vandelay Consulting") == -100
    assert s.prestige_bonus("Pied Piper") == 0  # tier with no bonus entry
    assert s.prestige_bonus("Nobody") == 0


def test_is_blocklisted_edges():
    s = _s({"blocklist": {"companies": ["Globex Bank"], "name_patterns": ["cyberdyne", "umbrella corp"]}})
    assert s.is_blocklisted("Globex Bank PLC")
    assert s.is_blocklisted("Cyberdyne Systems")
    assert s.is_blocklisted("Umbrella Corporation")  # suffix-stripped pattern still matches
    assert not s.is_blocklisted("")
    assert not s.is_blocklisted("Globex")  # single token is not a prefix match of "globex bank"
    assert not _s({}).is_blocklisted("Anything")


def test_merged_dream_list_dedupes_and_keeps_order():
    s = _s({
        "dream_list": ["Initech", "Hooli"],
        "prestige_tiers": {"sss": ["Initech, Inc.", "Aperture"], "ss": ["Hooli", "Soylent"], "a": ["Tyrell"]},
        "prestige_scoring": {"auto_dream": ["sss", "ss", "missing_tier"]},
    })
    assert s.merged_dream_list() == ["Initech", "Hooli", "Aperture", "Soylent"]
    assert s.is_dream("aperture") and not s.is_dream("Tyrell")
    assert _s({}).merged_dream_list() == []
    assert _s({"dream_list": ["X"]}).merged_dream_list() == ["X"]


def test_active_categories_and_keyword_helpers():
    s = Settings(
        root=Path("."),
        categories={"be": {"title_keywords": ["Backend Engineer"]}, "pm": {"title_keywords": ["PM"], "excluded": True},
                    "ops": {"title_keywords": ["SRE"]}, "note": "not a dict"},
        targets={"categories": {"excluded": ["ops"]}, "seniority": {"exclude_title_keywords": ["Senior"]},
                 "location": {"blocked_countries": ["xx", "Gb"], "country_aliases": {"xx": ["Freedonia"], "yy": None}}},
    )
    assert list(s.active_categories()) == ["be"]
    assert s.title_keywords() == {"be": ["backend engineer"]}
    assert s.excluded_title_keywords() == ["pm"]
    assert s.seniority_exclude_keywords() == ["senior"]
    assert s.blocked_countries() == ["XX", "GB"]
    assert s.country_aliases() == {"XX": ["freedonia"], "YY": []}
    assert Settings(root=Path("."), targets={"location": {"country_aliases": ["not", "a", "map"]}}).country_aliases() == {}


@pytest.mark.parametrize("fname,body,where", [
    ("pipeline.yaml", "paths: [jobs_dir]\n", "pipeline.yaml: paths"),
    ("pipeline.yaml", "outreach: true\n", "pipeline.yaml: outreach"),
    ("companies.yaml", "- Acme\n- Initech\n", "companies.yaml"),
    ("targets.yaml", "location: [US]\n", "targets.yaml: location"),
])
def test_settings_load_rejects_wrong_shapes(tmp_path, fname, body, where):
    root = _root(tmp_path)
    (root / "config" / fname).write_text(body)
    with pytest.raises(ConfigError, match=where):
        Settings.load(root)


@pytest.mark.parametrize("boards,msg", [
    ("boards: {company: Acme, ats: greenhouse, slug: acme}\n", "boards must be a list"),
    ("boards: [acme]\n", r"boards\[0\] must be a mapping"),
    ("boards: [{ats: greenhouse, slug: acme}]\n", r"boards\[0\] needs company and ats"),
    ("boards: [{company: Acme, ats: greenhouse}]\n", r"boards\[0\] \(greenhouse\) needs a slug"),
    ("boards: [{company: Acme, ats: lever, slug: ''}]\n", r"boards\[0\] \(lever\) needs a slug"),
])
def test_boards_shape_is_validated(tmp_path, boards, msg):
    root = _root(tmp_path)
    (root / "config" / "companies.yaml").write_text(boards)
    with pytest.raises(ConfigError, match=msg):
        Settings.load(root)


def test_custom_board_may_use_url_instead_of_slug(tmp_path):
    root = _root(tmp_path)
    (root / "config" / "companies.yaml").write_text("boards: [{company: Acme, ats: custom, url: 'https://acme.example/jobs'}]\n")
    assert Settings.load(root).boards[0]["ats"] == "custom"
