"""scripts/ui_perf.py --root on a small synthetic root: every screen answers and the index stays outside it."""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ui_perf", ROOT / "scripts" / "ui_perf.py")
ui_perf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui_perf)  # type: ignore[union-attr]

pytestmark = pytest.mark.integration
NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)


def test_measure_small_root_keeps_index_outside(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    root = ui_perf.synth(12, tmp_path / "root", now=NOW)["root"]
    res = ui_perf.measure(root, tmp_path / "ix" / "careeros.db", burst=False)
    assert res["jobs"] == 12 and set(res["screens_ms"]) == set(ui_perf.SCREENS)
    assert not (root / "data" / "careeros.db").exists() and (tmp_path / "ix" / "careeros.db").exists()
    assert "full reindex" in ui_perf.table(res)
