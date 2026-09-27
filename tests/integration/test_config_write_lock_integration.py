"""Config writes are serialised by one inter-process lock (data/locks/config.lock): two Settings saves from the
same page version -> exactly one lands, the other gets the stale-version conflict; `careeros advise apply` waits
for a save in progress instead of overwriting it. Category ids are checked against config/categories.yaml."""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import pytest
import yaml
from conftest import EXAMPLE_REPO, PY, make_temp_root, subprocess_env

from careeros.config import Settings
from careeros.runs import locks
from careeros.ui.services import settings_io
from careeros.ui.services.settings_io import SettingsConflict, SettingsInvalid

pytestmark = pytest.mark.integration


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = make_temp_root(tmp_path / "repo")
    (r / "config" / "pipeline.yaml").write_text((EXAMPLE_REPO / "config" / "pipeline.yaml").read_text())
    return r


def test_two_concurrent_saves_from_one_version_one_wins_one_conflicts(root, monkeypatch):
    v = settings_io.read_section(Settings.load(root), "runs")["version"]
    real_validate = settings_io.validate_root

    def slow_validate(r):  # widen the check -> write window so the saves overlap
        time.sleep(0.3)
        real_validate(r)

    monkeypatch.setattr(settings_io, "validate_root", slow_validate)
    start = threading.Barrier(2)
    results: dict[str, object] = {}

    def save(preset: str) -> None:
        start.wait()
        try:
            settings_io.save_section(Settings.load(root), "runs", {"pipeline:runs.preset": preset}, version=v)
            results[preset] = "ok"
        except SettingsConflict as e:
            results[preset] = e

    ts = [threading.Thread(target=save, args=(p,)) for p in ("small", "large")]
    for t in ts:
        t.start()
    for t in ts:
        t.join(10)
    oks = [p for p, r in results.items() if r == "ok"]
    conflicts = [p for p, r in results.items() if isinstance(r, SettingsConflict)]
    assert len(oks) == 1 and len(conflicts) == 1, results
    on_disk = yaml.safe_load((root / "config" / "pipeline.yaml").read_text())["runs"]["preset"]
    assert on_disk == oks[0]  # the winner's write is the one kept


def test_save_waits_for_the_lock_then_sees_the_new_version(root, monkeypatch):
    v = settings_io.read_section(Settings.load(root), "runs")["version"]
    monkeypatch.setattr(locks, "CONFIG_LOCK_TIMEOUT_S", 0.2)
    with locks.config_lock(root):
        with pytest.raises(SettingsConflict, match="Another save"):
            settings_io.save_section(Settings.load(root), "runs", {"pipeline:runs.preset": "small"}, version=v)
    settings_io.save_section(Settings.load(root), "runs", {"pipeline:runs.preset": "small"}, version=v)


def test_lock_file_lives_under_gitignored_data(root):
    assert locks.config_lock_path(root) == root / "data" / "locks" / "config.lock"


def _seed_snapshots(root: Path) -> None:
    from datetime import datetime, timedelta, timezone
    mb = 1024 * 1024
    runs = root / "data" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    lines = []
    for i, day in enumerate((21, 10, 0)):
        total = int((100 + 800 * i / 2) * mb)
        cats = {"postings": int(total * 0.8), "resumes_pdfs": 0, "screenshots": 0, "run_logs": 0, "tracker": 0,
                "other": total - int(total * 0.8)}
        lines.append(json.dumps({"at": (now - timedelta(days=day)).isoformat(), "trigger": "prune",
                                 "pruned_bytes": 0, "bytes": cats, "total": total,
                                 "disk": {"total": 10**12, "free": 5 * 10**11, "free_pct": 50.0}}))
    (runs / "storage.jsonl").write_text("\n".join(lines) + "\n")


def test_advise_apply_waits_for_a_save_in_progress(root, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _seed_snapshots(root)
    cfg = root / "config" / "pipeline.yaml"
    before = cfg.read_text()
    with locks.config_lock(root):
        p = subprocess.Popen([PY, "-m", "careeros.cli", "--root", str(root), "advise", "apply",
                              "tighten-unprepared_posting_days"], env=subprocess_env(root, home), cwd=root,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(2.0)
        assert p.poll() is None, p.communicate()  # still waiting on the lock
        assert cfg.read_text() == before
    out, err = p.communicate(timeout=60)
    assert p.returncode == 0, err
    assert yaml.safe_load(cfg.read_text())["retention"]["unprepared_posting_days"] == 60


def test_unknown_category_ids_are_refused_by_name(root):
    with pytest.raises(SettingsInvalid) as ei:
        settings_io.save_section(Settings.load(root), "targets",
                                 {"targets:categories.primary": ["swe_backend", "swe_bakend"]})
    assert ei.value.fields["targets:categories.primary"].startswith("Unknown categories id: swe_bakend. Known in")


def test_category_fields_offer_the_ids_from_categories_yaml(root):
    known = set(yaml.safe_load((root / "config" / "categories.yaml").read_text()))
    sec = settings_io.read_section(Settings.load(root), "targets")["section"]
    fields = {f["id"]: f for g in sec["groups"] for f in g["items"] if "id" in f}
    for fid in ("targets:categories.primary", "targets:categories.secondary", "targets:categories.excluded"):
        assert set(fields[fid]["options"]) == known and fields[fid]["strict_options"] is False
