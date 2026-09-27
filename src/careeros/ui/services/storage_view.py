"""Response shapes of the Storage & efficiency GETs (GET /api/storage, GET /api/advise), typed for the OpenAPI
schema the frontend generates its types from (ui/openapi.json -> ui/src/api/schema.gen.ts, docs/UI.md).

The dicts come from careeros.runs.storage (measure, load_snapshots), careeros.runs.advisor (load_advisor_config,
advise); these TypedDicts only describe them. A TypedDict response drops unlisted keys, so every key those
functions can write is listed; numbers that can be int or float are `int | float` so ints stay ints on the wire."""
from __future__ import annotations

from typing import Any, Union

from typing_extensions import NotRequired, TypedDict

Num = Union[int, float]


class DiskUsage(TypedDict):
    total: int
    free: int
    free_pct: Num


class StorageSnapshot(TypedDict):
    """One line of the snapshots log (appended after each run / prune; older lines may lack keys)."""
    at: NotRequired[str]
    trigger: NotRequired[str]
    pruned_bytes: NotRequired[int | None]
    bytes: NotRequired[dict[str, int]]
    total: int
    disk: NotRequired[DiskUsage]


class StorageLimits(TypedDict):
    budget_mb: Num
    warn_at_pct: Num
    disk_free_warn_pct: Num


class AdvisorLimits(TypedDict):
    advise_after_days: Num
    prune_idle_weeks: Num
    min_runs: Num
    window_days: Num
    usage_limit_stops: Num
    failure_rate_warn: Num


class AdvisorConfig(TypedDict):
    storage: StorageLimits
    advisor: AdvisorLimits


class StorageView(TypedDict):
    """GET /api/storage: bytes per category, the disk, the snapshot history and the advisor config."""
    bytes: dict[str, int]
    total: int
    disk: DiskUsage
    snapshots: list[StorageSnapshot]
    config: AdvisorConfig


# "from" is a keyword, hence the functional form.
RecommendationChange = TypedDict("RecommendationChange", {"file": str, "path": str, "from": Any, "to": Any})
Projection = TypedDict("Projection", {"30d": int, "90d": int})


class Recommendation(TypedDict):
    id: str
    kind: str
    severity: str
    title: str
    why: str
    change: RecommendationChange | None


class StorageAdvice(TypedDict):
    ready: bool
    days: Num
    need_days: Num
    current: NotRequired[int]
    rate_per_day: NotRequired[int]
    projection: NotRequired[Projection]
    budget: NotRequired[int]
    recommendations: list[Recommendation]


class RunMetrics(TypedDict):
    runs: int
    attempts: int
    failed: int
    avg_job_s: Num
    p90_job_s: Num
    failure_rate: Num
    budget_used: Num
    stops: dict[str, int]  # stop_reason -> count; a run without one counts as "unknown"
    prepare_share: NotRequired[Num | None]


class RunsAdvice(TypedDict):
    ready: bool
    min_runs: Num
    metrics: dict[str, RunMetrics]
    recommendations: list[Recommendation]


class Advice(TypedDict):
    """GET /api/advise: storage and run advice plus every recommendation (storage first)."""
    storage: StorageAdvice
    runs: RunsAdvice
    recommendations: list[Recommendation]
