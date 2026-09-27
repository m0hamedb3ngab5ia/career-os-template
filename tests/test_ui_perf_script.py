"""scripts/ui_perf.py: the synthetic-data generator writes the real on-disk shape (small N), so the one-off UI
performance baseline keeps working as the code moves."""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ui_perf", ROOT / "scripts" / "ui_perf.py")
ui_perf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui_perf)  # type: ignore[union-attr]

pytestmark = pytest.mark.unit
NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)


def test_synth_writes_real_shape(tmp_path):
    info = ui_perf.synth(40, tmp_path / "root", now=NOW)
    root = info["root"]
    jobs = [d for d in (root / "data" / "jobs").iterdir() if d.is_dir()]
    assert info["jobs"] == len(jobs) == 40 and info["tracker_rows"] == 40
    assert (root / "data" / "JobTracker.xlsx").is_file()
    assert all((d / "posting.json").is_file() and (d / "status.json").is_file() for d in jobs)
    assert info["contacts"] >= 4 and sum((d / "contacts.json").exists() for d in jobs) == info["contacts"]
    assert sum((d / "outreach.json").exists() for d in jobs) == info["outreach"]
    assert len(set(info["statuses"].values())) >= 4          # a mix, not one status
    text = " ".join(p.read_text() for d in jobs for p in d.glob("*.json"))
    assert "@" not in text.replace("@example.com", "")         # fictional addresses only
    assert all(json.loads((d / "posting.json").read_text())["company"].startswith("Acme ") for d in jobs)


def test_synth_is_deterministic(tmp_path):
    a = ui_perf.synth(15, tmp_path / "a", now=NOW)
    b = ui_perf.synth(15, tmp_path / "b", now=NOW)
    assert a["statuses"] == b["statuses"]


def test_history_ends_at_status():
    for st in ui_perf.MIX:
        h = ui_perf._history(st, NOW)
        assert h[0]["status"] == "found" and h[-1]["status"] == st
