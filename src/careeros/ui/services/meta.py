"""GET /api/meta: every code the frontend renders (statuses, tiers, action types, stop reasons, presets) and the
UI settings, read from the config and the models so a new status or action type needs no frontend change."""
from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict

from careeros.models import ACTION_NEEDS, ACTION_TYPES
from careeros.runs.config import PRESET_NAMES, RECOMMENDED_PRESET, load_runs_config
from careeros.runs.runner import CLEAN_STOPS, STOP_REASONS
from careeros.ui.config import load_ui_config

TIERS = ["A", "B", "C"]
PRIORITIES = ["H", "M", "L"]
SAFETY_VERDICTS = ["pass", "review", "block", "skip"]
# `error`: a single-call run (inbox sync) failed or a run crashed (runner.execute_run); not in STOP_REASONS.
# `busy`: a UI step (scout/prune) lost the race for the pipeline lock after the UI said started (ui.services.step).
EXTRA_STOPS = ["error", "busy"]


# Response shapes: FastAPI turns these into the OpenAPI schema that ui/src/api/schema.gen.ts is generated from.
class Presets(TypedDict):
    names: list[str]
    values: dict[str, dict[str, int]]
    recommended: str
    current: str


class ColumnConfig(TypedDict):
    name: str
    statuses: list[str]


class PipelineConfig(TypedDict):
    columns: list[ColumnConfig]
    closed: list[str]


class UiSettings(TypedDict):
    theme: str
    undo_seconds: int
    page_size: int
    due_soon_hours: int
    pause_until_tomorrow_at: str


class Meta(TypedDict):
    statuses: list[str]
    tiers: list[str]
    priorities: list[str]
    action_types: list[str]
    action_needs: list[str]
    safety_verdicts: list[str]
    stop_reasons: list[str]
    clean_stops: list[str]
    presets: Presets
    pipeline: PipelineConfig
    ui: UiSettings


def meta(settings: Any) -> Meta:
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
        "ui": {"theme": ui.theme, "undo_seconds": ui.undo_seconds, "page_size": ui.page_size,
               "due_soon_hours": ui.due_soon_hours, "pause_until_tomorrow_at": ui.pause_until_tomorrow_at},
    }
