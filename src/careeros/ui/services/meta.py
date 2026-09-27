"""GET /api/meta: every code the frontend renders (statuses, tiers, action types, stop reasons, presets) and the
UI settings, read from the config and the models so a new status or action type needs no frontend change."""
from __future__ import annotations

from typing import Any

from careeros.models import ACTION_NEEDS, ACTION_TYPES
from careeros.runs.config import PRESET_NAMES, RECOMMENDED_PRESET, load_runs_config
from careeros.runs.runner import CLEAN_STOPS, STOP_REASONS
from careeros.ui.config import load_ui_config

TIERS = ["A", "B", "C"]
PRIORITIES = ["H", "M", "L"]
SAFETY_VERDICTS = ["pass", "review", "block", "skip"]
# `error`: a single-call run (inbox sync) failed or a run crashed (runner.execute_run); not in STOP_REASONS.
EXTRA_STOPS = ["error"]


def meta(settings: Any) -> dict[str, Any]:
    ui = load_ui_config(settings)
    runs = load_runs_config(settings)
    return {
        "statuses": list(settings.lifecycle_statuses),
        "tiers": TIERS,
        "priorities": PRIORITIES,
        "action_types": list(ACTION_TYPES),
        "action_needs": list(ACTION_NEEDS),
        "safety_verdicts": SAFETY_VERDICTS,
        "stop_reasons": list(STOP_REASONS) + EXTRA_STOPS,
        "clean_stops": list(CLEAN_STOPS),
        "presets": {"names": list(PRESET_NAMES), "values": {k: dict(v) for k, v in runs.presets.items()},
                    "recommended": RECOMMENDED_PRESET, "current": runs.preset},
        "pipeline": {"columns": ui.columns, "closed": ui.closed},
        "ui": {"theme": ui.theme, "undo_seconds": ui.undo_seconds, "page_size": ui.page_size},
    }
