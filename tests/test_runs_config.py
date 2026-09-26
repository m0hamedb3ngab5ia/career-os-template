from __future__ import annotations

import copy

import pytest
import yaml
from conftest import EXAMPLE_REPO

from careeros.config import ConfigError
from careeros.runs.config import (
    DEFAULT_HEADLESS_CMD,
    DEFAULT_PRESETS,
    RECOMMENDED_PRESET,
    budget_for,
    load_runs_config,
)

pytestmark = pytest.mark.unit


class S:
    def __init__(self, pipeline):
        self.pipeline = pipeline


def example_pipeline() -> dict:
    return yaml.safe_load((EXAMPLE_REPO / "config" / "pipeline.yaml").read_text())


def test_defaults_without_runs_block():
    cfg = load_runs_config(S({}))
    assert cfg.preset == RECOMMENDED_PRESET == "medium"
    assert cfg.presets["medium"] == DEFAULT_PRESETS["medium"]
    assert cfg.headless_cmd == DEFAULT_HEADLESS_CMD


def test_example_config_matches_code_defaults():
    ex = load_runs_config(S(example_pipeline()))
    d = load_runs_config(S({}))
    assert ex.presets == d.presets and ex.preset == d.preset and ex.ranking == d.ranking
    assert ex.headless_cmd == d.headless_cmd and ex.allowed_tools == d.allowed_tools
    assert ex.job_timeout_minutes == d.job_timeout_minutes


def test_default_headless_cmd_streams_and_never_prompts():
    cmd = DEFAULT_HEADLESS_CMD
    assert cmd[:2] == ["claude", "-p"]
    assert cmd[cmd.index("--output-format") + 1] == "stream-json" and "--verbose" in cmd
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"


@pytest.mark.parametrize("preset", ["small", "medium", "large", "max"])
def test_budget_presets(preset):
    cfg = load_runs_config(S({}))
    b = budget_for(cfg, "score", preset=preset)
    assert b.preset == preset
    assert b.max_jobs == DEFAULT_PRESETS[preset]["max_score_jobs"]
    assert b.max_minutes == DEFAULT_PRESETS[preset]["max_minutes"]
    assert budget_for(cfg, "prepare", preset=preset).max_jobs == DEFAULT_PRESETS[preset]["max_prepare_jobs"]


def test_presets_grow():
    p = DEFAULT_PRESETS
    for key in ("max_score_jobs", "max_prepare_jobs", "max_minutes"):
        assert p["small"][key] < p["medium"][key] < p["large"][key] < p["max"][key]


def test_custom_preset_and_cli_overrides():
    cfg = load_runs_config(S({"runs": {"preset": "custom",
                                       "custom": {"max_score_jobs": 7, "max_prepare_jobs": 2, "max_minutes": 15}}}))
    b = budget_for(cfg, "score")
    assert (b.preset, b.max_jobs, b.max_minutes) == ("custom", 7, 15)
    o = budget_for(cfg, "score", max_jobs=3, max_minutes=9)
    assert (o.preset, o.max_jobs, o.max_minutes) == ("custom", 3, 9)


def test_preset_override_in_yaml():
    cfg = load_runs_config(S({"runs": {"presets": {"small": {"max_score_jobs": 4}}}}))
    assert cfg.presets["small"]["max_score_jobs"] == 4
    assert cfg.presets["small"]["max_minutes"] == DEFAULT_PRESETS["small"]["max_minutes"]


@pytest.mark.parametrize("bad", [
    {"runs": []},
    {"runs": {"preset": "huge"}},
    {"runs": {"presets": {"small": {"max_score_jobs": 0}}}},
    {"runs": {"presets": {"small": {"max_minutes": "lots"}}}},
    {"runs": {"presets": {"tiny": {}}}},
    {"runs": {"job_timeout_minutes": {"score": -1}}},
    {"runs": {"max_consecutive_failures": 0}},
    {"runs": {"ranking": {"freshness_weight": "high"}}},
    {"runs": {"ranking": {"bogus": 1}}},
    {"runs": {"custom": {"max_jobs": 5}}},
    {"runs": {"stop_on_timeout": "yes"}},
    {"llm": {"headless_cmd": "claude -p"}},
    {"llm": {"allowed_tools": "Read"}},
    {"runs": {"usage_limit_patterns": ["("]}},
])
def test_invalid_config_fails_closed(bad):
    with pytest.raises(ConfigError):
        load_runs_config(S(bad))


def test_budget_rejects_bad_overrides():
    cfg = load_runs_config(S({}))
    with pytest.raises(ValueError):
        budget_for(cfg, "score", max_jobs=0)
    with pytest.raises(ValueError):
        budget_for(cfg, "score", preset="nope")


def test_example_file_marks_recommended_defaults():
    text = (EXAMPLE_REPO / "config" / "pipeline.yaml").read_text()
    runs = text[text.index("\nruns:"):]
    assert "medium" in runs and "(Recommended)" in runs
    assert runs.count("(Recommended)") >= 5
    data = copy.deepcopy(example_pipeline())
    assert data["runs"]["preset"] == "medium"
