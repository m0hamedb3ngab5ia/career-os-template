"""REQ-165: GET /api/catalogue parses docs/CATALOGUE.md into sections and rows."""
from __future__ import annotations

import pytest
from conftest import make_temp_root
from fastapi.testclient import TestClient
from fixtures.ui_data import build_ui_data
from datetime import datetime, timezone

from careeros.ui.app import create_app
from careeros.ui.index import Index
from careeros.ui.security import LOOPBACK
from careeros.ui.services.catalogue import parse_catalogue

pytestmark = pytest.mark.unit

MD = """# Feature catalogue

Everything it can do.
Full flags: [COMMANDS.md](COMMANDS.md).

## Start here

1. Not a table.
**Strategy:** fresh first.

## 1. Set up

| Feature | What it does | How to use | REQ |
|---|---|---|---|
| Init | Copies the example. | `careeros init`; or "set me up" | |
| Run | Runs steps. | `careeros run score|prepare` | REQ-102, REQ-103 |
| Locks | Locks a job. | `careeros job lock\\|unlock <id>` | |

## 2. Find jobs

| Feature | What it does | How to use | REQ |
|---|---|---|---|
| Scout | Pulls boards. | `careeros scout --sync` | |
"""


def test_parse_sections_rows_and_intro():
    c = parse_catalogue(MD)
    assert c.intro == ["Everything it can do.", "Full flags: COMMANDS.md."]
    assert [s.title for s in c.sections] == ["Start here", "1. Set up", "2. Find jobs"]
    assert c.sections[0].notes == ["1. Not a table.", "Strategy: fresh first."] and c.sections[0].rows == []
    assert c.sections[1].notes == []
    assert c.sections[1].rows[0].model_dump() == {
        "feature": "Init", "what": "Copies the example.", "how": '`careeros init`; or "set me up"', "req": ""}
    run = c.sections[1].rows[1]
    assert run.how == "`careeros run score|prepare`"  # a pipe inside code does not split the cell
    assert run.req == "REQ-102, REQ-103"
    assert c.sections[1].rows[2].how == "`careeros job lock|unlock <id>`"  # markdown \\| unescaped


def test_real_catalogue_parses():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "docs" / "CATALOGUE.md").read_text(encoding="utf-8")
    c = parse_catalogue(text)
    assert len(c.sections) >= 5 and all(r.feature and r.what for s in c.sections for r in s.rows)


def test_endpoint_and_missing_file(tmp_path):
    now = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)
    d = build_ui_data(make_temp_root(tmp_path / "repo"), now)
    ix = Index(d["settings"])
    ix.rebuild()
    app = create_app(d["settings"], index=ix, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=tmp_path / "no-static", now=lambda: now)
    root = d["settings"].root
    with TestClient(app) as c:
        (root / "docs").mkdir(exist_ok=True)
        (root / "docs" / "CATALOGUE.md").unlink(missing_ok=True)
        assert c.get("/api/catalogue").status_code == 404
        (root / "docs" / "CATALOGUE.md").write_text(MD, encoding="utf-8")
        body = c.get("/api/catalogue").json()
        assert body["sections"][2]["rows"][0]["feature"] == "Scout"
    ix.close()
