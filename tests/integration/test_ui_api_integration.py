"""The UI server end to end: FastAPI TestClient over a temp repo root with the fictional UI data, the static
frontend fallback, the request guard, and `careeros ui` as a real subprocess (health, then live SSE on a file
change)."""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

import pytest
from conftest import make_temp_root, subprocess_env
from fixtures.ui_data import build_ui_data

pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from careeros.store import Store  # noqa: E402
from careeros.ui.app import create_app  # noqa: E402
from careeros.ui.index import Index  # noqa: E402
from careeros.ui.security import LOOPBACK  # noqa: E402

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def data(tmp_path):
    return build_ui_data(make_temp_root(tmp_path / "repo"), NOW)


@pytest.fixture
def client(data, tmp_path):
    ix = Index(data["settings"])
    ix.rebuild()
    app = create_app(data["settings"], index=ix, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=tmp_path / "no-static", now=lambda: NOW)
    with TestClient(app) as c:
        yield c
    ix.close()


def test_health_and_meta(client):
    h = client.get("/api/health").json()
    assert h["ok"] is True and h["indexed_at"] and h["config_error"] is None
    m = client.get("/api/meta").json()
    assert "needs_review" in m["statuses"] and m["presets"]["recommended"] == "medium"


def test_status(client):
    st = client.get("/api/status").json()
    assert st["tiles"]["needs_you"]["value"] == 3 and st["counts"]["jobs"] == 8
    assert st["tiles"]["applied_week"]["value"] == 1


def test_jobs_list_filters_and_paging(client):
    page = client.get("/api/jobs", params={"limit": 2}).json()
    assert page["total"] == 8 and len(page["items"]) == 2 and page["next_cursor"] == "2"
    applied = client.get("/api/jobs", params=[("status", "applied"), ("status", "interview")]).json()
    assert {j["company"] for j in applied["items"]} == {"Hooli", "Stark Industries"}
    assert client.get("/api/jobs", params={"q": "initech"}).json()["total"] == 1
    assert client.get("/api/jobs", params={"sort": "bogus"}).status_code == 400
    assert client.get("/api/jobs", params={"limit": 0}).status_code == 422


def test_job_detail(client, data):
    jid = data["jobs"]["review"]
    d = client.get(f"/api/jobs/{jid}").json()
    assert d["job"]["company"] == "Umbrella Labs" and d["safety"]["verdict"] == "review"
    assert client.get("/api/jobs/nope00000000").status_code == 404
    assert client.get("/api/jobs/..%2Fconfig").status_code == 404


def test_guard_refuses_foreign_host_origin_and_headerless_writes(client):
    assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 421
    assert client.get("/api/health", headers={"origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/health").status_code == 403
    assert client.post("/api/health", headers={"x-careeros": "1"}).status_code in (404, 405)  # past the guard


def test_placeholder_page_without_a_built_frontend(client):
    r = client.get("/")
    assert r.status_code == 200 and "careeros ui" in r.text and "/api/health" in r.text
    assert client.get("/api/nope").status_code == 404


def test_static_frontend_and_spa_fallback(data, tmp_path):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    (static / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("no", encoding="utf-8")
    ix = Index(data["settings"])
    ix.rebuild()
    app = create_app(data["settings"], index=ix, allowed_hosts=LOOPBACK | {"testserver"}, static_dir=static)
    with TestClient(app) as c:
        assert c.get("/").text.startswith("<!doctype html>")
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/jobs/abc123").text.startswith("<!doctype html>")          # client-side route
        assert c.get("/..%2Fsecret.txt").text != "no"
        assert c.get("/assets/..%2F..%2Fsecret.txt").text != "no"
        assert c.get("/api/unknown").status_code == 404
    ix.close()


def test_config_error_is_reported_not_fatal(data, client):
    (data["settings"].root / "config" / "pipeline.yaml").write_text("ui: {theme: blue}\n", encoding="utf-8")
    client.app.state.ctx.reload_settings()
    h = client.get("/api/health").json()
    assert "ui.theme" in h["config_error"]
    assert client.get("/api/status").status_code == 200        # still serving with the last good settings


# --- real server ------------------------------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_health(url: str, proc: subprocess.Popen, timeout: float = 20) -> dict:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if proc.poll() is not None:
            raise AssertionError(f"careeros ui exited {proc.returncode}: {proc.stdout.read()}")
        try:
            return httpx.get(url + "/api/health", timeout=1).json()
        except httpx.HTTPError:
            time.sleep(0.2)
    raise AssertionError("careeros ui did not answer /api/health")


@pytest.fixture
def server(data, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    port = _free_port()
    env = subprocess_env(data["settings"].root, home)
    proc = subprocess.Popen([sys.executable, "-m", "careeros.cli", "ui", "--no-open", "--port", str(port)],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    url = f"http://127.0.0.1:{port}"
    try:
        yield url, _wait_health(url, proc)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_cli_serves_health_and_indexes_on_start(server, data):
    url, health = server
    assert health["ok"] is True
    assert httpx.get(url + "/api/status").json()["counts"]["jobs"] == 8
    assert (data["settings"].paths["jobs_dir"].parent / "careeros.db").exists()


def test_cli_pushes_an_sse_event_when_a_job_file_changes(server, data):
    url, _ = server
    jid = data["jobs"]["queued"]
    events = []
    with httpx.stream("GET", url + "/api/events", timeout=httpx.Timeout(15.0)) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        lines = r.iter_lines()
        for line in lines:                                   # the hello frame first
            if line.startswith("event: hello"):
                break
        Store(data["settings"]).set_status(jid, "prepared", "docs ready")
        cur = {}
        deadline = time.monotonic() + 15
        for line in lines:
            if line.startswith("event: "):
                cur["event"] = line[7:]
            elif line.startswith("data: "):
                cur["data"] = json.loads(line[6:])
            elif line == "" and cur:
                events.append(cur)
                if cur.get("event") == "changed" and jid in cur["data"]["jobs"]:
                    break
                cur = {}
            if time.monotonic() > deadline:
                break
    assert any(e.get("event") == "changed" and jid in e["data"]["jobs"] for e in events), events
    job = httpx.get(f"{url}/api/jobs/{jid}").json()
    assert job["job"]["status"] == "prepared"


def test_cli_refuses_a_non_loopback_host(data, tmp_path):
    home = tmp_path / "h2"
    home.mkdir()
    r = subprocess.run([sys.executable, "-m", "careeros.cli", "ui", "--no-open", "--host", "0.0.0.0"],
                       env=subprocess_env(data["settings"].root, home), capture_output=True, text=True, timeout=30)
    assert r.returncode == 2 and "127.0.0.1" in r.stderr


def test_cli_reindex_flag_rebuilds(data, tmp_path):
    db = data["settings"].paths["jobs_dir"].parent / "careeros.db"
    db.write_bytes(b"not a database")
    home = tmp_path / "h3"
    home.mkdir()
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "careeros.cli", "ui", "--no-open", "--reindex", "--port",
                             str(port)], env=subprocess_env(data["settings"].root, home), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    try:
        _wait_health(f"http://127.0.0.1:{port}", proc)
        assert httpx.get(f"http://127.0.0.1:{port}/api/status").json()["counts"]["jobs"] == 8
    finally:
        proc.terminate()
        proc.wait(timeout=10)

