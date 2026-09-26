"""Settings and Storage & efficiency API end to end: FastAPI TestClient over a temp repo root with the fictional UI
data. Section list, read, diff, save (200 / 422 per field with the file rolled back / 409 on a stale version),
reset to recommended, the ranking preview, storage, advice (+ apply) and prune (dry run first, then a step run)."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone

import pytest
from conftest import EXAMPLE_REPO, make_temp_root
from fixtures.ui_data import build_ui_data

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from careeros.runs.store import RunStore, iso  # noqa: E402
from careeros.ui.app import create_app  # noqa: E402
from careeros.ui.index import Index  # noqa: E402
from careeros.ui.routers import storage as storage_router  # noqa: E402
from careeros.ui.security import LOOPBACK  # noqa: E402

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)
W = {"X-CareerOS": "1"}


@pytest.fixture
def data(tmp_path):
    root = make_temp_root(tmp_path / "repo")
    shutil.copy(EXAMPLE_REPO / "config" / "pipeline.yaml", root / "config" / "pipeline.yaml")  # keep comments
    d = build_ui_data(root, NOW)
    d["root"] = root
    return d


@pytest.fixture
def client(data, tmp_path):
    ix = Index(data["settings"])
    ix.rebuild()
    app = create_app(data["settings"], index=ix, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=tmp_path / "no-static", now=lambda: NOW)
    with TestClient(app) as c:
        yield c
    ix.close()


def test_section_list_in_schema_order(client):
    out = client.get("/api/settings").json()
    ids = [s["id"] for s in out["sections"]]
    assert ids[:10] == ["general", "targets", "autonomy", "safety", "scout", "companies", "outreach",
                        "notifications", "runs", "storage"]
    runs = next(s for s in out["sections"] if s["id"] == "runs")
    assert runs["title"] == "Runs & schedule" and runs["files"] == ["pipeline"]


def test_read_section_has_schema_values_defaults_and_relative_files(client, data):
    out = client.get("/api/settings/autonomy").json()
    assert out["section"]["id"] == "autonomy"
    assert out["values"]["targets:tiers.A.auto_submit"] is False
    assert out["defaults"]["targets:volume.max_applications_per_day"] == 15
    assert out["files"] == {"pipeline": "config/pipeline.yaml", "targets": "config/targets.yaml"}
    assert out["version"]
    assert client.get("/api/settings/nope").status_code == 404


def test_diff_writes_nothing(client, data):
    p = data["root"] / "config" / "pipeline.yaml"
    before = p.read_text()
    r = client.post("/api/settings/runs/diff", json={"changes": {"pipeline:runs.preset": "large"}}, headers=W)
    assert r.status_code == 200
    assert "+  preset: large" in r.json()["diffs"]["pipeline"] and p.read_text() == before


def test_writes_need_the_header(client):
    r = client.put("/api/settings/runs", json={"changes": {"pipeline:runs.preset": "large"}})
    assert r.status_code == 403


def test_save_then_read_back(client, data):
    v = client.get("/api/settings/runs").json()["version"]
    r = client.put("/api/settings/runs", json={"changes": {"pipeline:runs.preset": "small"}, "version": v},
                   headers=W)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["old"] == {"pipeline:runs.preset": "medium"} and body["version"] != v
    assert client.get("/api/settings/runs").json()["values"]["pipeline:runs.preset"] == "small"
    assert "preset: small" in (data["root"] / "config" / "pipeline.yaml").read_text()


def test_invalid_save_is_422_per_field_and_rolls_back(client, data):
    p = data["root"] / "config" / "targets.yaml"
    before = p.read_text()
    r = client.put("/api/settings/safety", json={"changes": {
        "targets:safety.ghost.very_old_post_days": 20}}, headers=W)
    assert r.status_code == 422
    body = r.json()
    assert "Old post" in body["fields"]["targets:safety.ghost.very_old_post_days"]
    assert body["general"] == [] and "1 error" in body["detail"]
    assert p.read_text() == before


def test_loader_error_maps_to_field_and_rolls_back(client, data):
    p = data["root"] / "config" / "pipeline.yaml"
    before = p.read_text()
    r = client.put("/api/settings/storage", json={"changes": {"pipeline:retention.run_summaries_days": 10}},
                   headers=W)
    assert r.status_code == 422
    assert "run_summaries_days" in r.json()["fields"]["pipeline:retention.run_summaries_days"]
    assert p.read_text() == before


def test_stale_version_is_409(client):
    v = client.get("/api/settings/runs").json()["version"]
    assert client.put("/api/settings/runs", json={"changes": {"pipeline:runs.preset": "small"}, "version": v},
                      headers=W).status_code == 200
    r = client.put("/api/settings/runs", json={"changes": {"pipeline:runs.preset": "large"}, "version": v},
                   headers=W)
    assert r.status_code == 409 and "changed" in r.json()["detail"]


def test_reset_group_proposes_recommended_values_without_writing(client, data):
    client.put("/api/settings/runs", json={"changes": {"pipeline:runs.ranking.freshness_weight": 10}}, headers=W)
    r = client.post("/api/settings/runs/reset/ranking", headers=W)
    assert r.status_code == 200
    assert r.json()["changes"]["pipeline:runs.ranking.freshness_weight"] == 60
    assert client.get("/api/settings/runs").json()["values"]["pipeline:runs.ranking.freshness_weight"] == 10
    assert client.post("/api/settings/runs/reset/nope", headers=W).status_code == 404


def test_ranking_preview_uses_the_draft_weights(client, data):
    base = client.post("/api/settings/runs/ranking-preview", json={"kind": "score", "weights": {}},
                       headers=W).json()
    assert base["kind"] == "score" and base["total"] >= 1 and len(base["items"]) <= 5
    top = base["items"][0]
    assert {"company", "title", "score", "why", "rank"} <= set(top)
    zero = client.post("/api/settings/runs/ranking-preview",
                       json={"kind": "score", "weights": {"freshness_weight": 0}}, headers=W).json()
    assert all(i["score"] == 0 for i in zero["items"])
    bad = client.post("/api/settings/runs/ranking-preview",
                      json={"kind": "score", "weights": {"nope": 1}}, headers=W)
    assert bad.status_code == 400
    assert client.post("/api/settings/runs/ranking-preview", json={"kind": "apply", "weights": {}},
                       headers=W).status_code == 400


def test_storage_and_advice(client, data):
    st = client.get("/api/storage").json()
    assert set(st["bytes"]) >= {"postings", "screenshots", "run_logs"} and st["total"] > 0
    assert st["snapshots"] == [] and st["config"]["storage"]["budget_mb"] == 1024
    adv = client.get("/api/advise").json()
    assert adv["storage"]["ready"] is False and adv["recommendations"] == []


def _seed_snapshots(root, settings):
    rs = RunStore(settings)
    rs.dir.mkdir(parents=True, exist_ok=True)
    mb = 1024 * 1024
    lines = []
    for i in range(3):
        at = NOW - timedelta(days=20 - i * 10)
        shots = (100 + i * 400) * mb
        lines.append({"at": iso(at), "trigger": "prune", "pruned_bytes": 0,
                      "bytes": {"postings": 5 * mb, "resumes_pdfs": mb, "screenshots": shots, "run_logs": mb,
                                "tracker": 0, "other": 0},
                      "total": shots + 7 * mb, "disk": {"total": 100 * 1024 * mb, "free": 50 * 1024 * mb,
                                                        "free_pct": 50.0}})
    (rs.dir / "storage.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))


def test_advice_apply_writes_the_change_and_refuses_unknown(client, data):
    _seed_snapshots(data["root"], data["settings"])
    adv = client.get("/api/advise").json()
    rec = next(r for r in adv["recommendations"] if r["change"])
    assert rec["id"] == "tighten-screenshots_after_closed_days"
    r = client.post(f"/api/advise/{rec['id']}/apply", headers=W)
    assert r.status_code == 200, r.text
    assert r.json()["to"] == rec["change"]["to"]
    vals = client.get("/api/settings/storage").json()["values"]
    assert vals["pipeline:retention.screenshots_after_closed_days"] == rec["change"]["to"]
    assert client.post("/api/advise/nope/apply", headers=W).status_code == 404


def test_prune_dry_run_then_start(client, monkeypatch):
    plan = client.post("/api/prune", json={"dry_run": True}, headers=W)
    assert plan.status_code == 200
    body = plan.json()
    assert body["dry_run"] is True and "summary" in body and isinstance(body["items"], list)

    started = {}

    class FakeRC:
        def __init__(self, settings, now):
            pass

        def start_step(self, kind):
            started["kind"] = kind
            return {"kind": kind, "started": True, "pid": 123, "output": "x"}

    monkeypatch.setattr(storage_router, "RunControl", FakeRC)
    r = client.post("/api/prune", json={"dry_run": False}, headers=W)
    assert r.status_code == 200 and r.json()["started"] is True and started == {"kind": "prune"}
