"""Typed responses for Today, Jobs (list + tabs), Job detail and Pipeline: each endpoint returns exactly the JSON
its service builds (no key dropped by FastAPI's response filtering once the routes carry TypedDict shapes), pinned
by a snapshot on the fictional UI data. Refresh with CAREEROS_UPDATE_SNAPSHOTS=1 (see docs/UI.md)."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from conftest import make_temp_root
from fixtures.ui_data import add_outreach_data, build_ui_data

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from careeros.ui.app import create_app  # noqa: E402
from careeros.ui.index import Index  # noqa: E402
from careeros.ui.security import LOOPBACK  # noqa: E402

pytestmark = pytest.mark.integration

SNAPSHOTS = Path(__file__).resolve().parents[1] / "fixtures" / "ui_snapshots"
NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)?")
ENDPOINTS = {
    "today": "/api/today?tz=UTC",
    "jobs": "/api/jobs?limit=5",
    "jobs_tab_applied": "/api/jobs?tab=applied",
    "jobs_tabs": "/api/jobs/tabs",
    "job_review": "/api/jobs/{review}",
    "job_interview": "/api/jobs/{interview}",
    "job_applied": "/api/jobs/{applied}",
    "pipeline": "/api/pipeline",
}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("TZ", "UTC")        # local-time stamps: pin the zone
    import time
    time.tzset()
    root = make_temp_root(tmp_path / "repo")
    data = add_outreach_data(build_ui_data(root, NOW))
    ix = Index(data["settings"])
    ix.rebuild()
    app = create_app(data["settings"], index=ix, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=tmp_path / "no-static", now=lambda: NOW)
    with TestClient(app) as c:
        yield c, data, tmp_path
    ix.close()
    monkeypatch.delenv("TZ")
    time.tzset()


def _stable(body: object, data: dict, tmp: Path) -> object:
    """Swap per-build values (temp paths, generated ids, wall-clock stamps, file mtimes) for placeholders; every
    key stays."""
    text = json.dumps(body).replace(str(tmp.resolve()), "<tmp>").replace(str(tmp), "<tmp>")
    for key, jid in data["jobs"].items():
        text = text.replace(jid, f"<job:{key}>")
    for key, aid in data["actions"].items():
        text = text.replace(str(aid), f"<action:{key}>")
    # Fixture stamps sit at or before NOW; later ones are the wall clock (log.md lines, status writes).
    text = STAMP.sub(lambda m: "<wall>" if m[0][:10] > "2026-09-25" else m[0], text)

    def walk(v: object) -> object:
        if isinstance(v, dict):
            return {k: ("<mtime>" if k == "modified" else
                        "<created>" if k == "created" and isinstance(x, str) else walk(x)) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return v

    return walk(json.loads(text))


@pytest.mark.parametrize("name", list(ENDPOINTS))
def test_response_matches_snapshot(env, name):
    client, data, tmp = env
    res = client.get(ENDPOINTS[name].format(**data["jobs"]))
    assert res.status_code == 200, res.text
    got = _stable(res.json(), data, tmp)
    snap = SNAPSHOTS / f"{name}.json"
    if os.environ.get("CAREEROS_UPDATE_SNAPSHOTS"):
        snap.write_text(json.dumps(got, indent=2, sort_keys=True) + "\n")
    assert got == json.loads(snap.read_text())
    assert not re.search(r"/(private|tmp|var|Users)/", json.dumps(got)), "a machine path leaked into the snapshot"
