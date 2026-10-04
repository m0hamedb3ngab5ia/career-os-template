"""`careeros apply fill`: refusal paths via the CLI, and a real headless fill of a saved GH-like form."""
from __future__ import annotations

import functools
import http.server
import json
import subprocess
import threading
from pathlib import Path

import pytest
from conftest import FIXTURES, PY, ready_env, subprocess_env

pytestmark = pytest.mark.integration
GH = FIXTURES / "greenhouse"


def _fields(tmp_path: Path) -> list[dict]:
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = [("first_name", "text", "Alex"), ("email", "text", "alex@example.com"), ("question_1", "textarea", "Fit."),
         ("resume", "file", str(pdf)), ("question_2", "checkbox_group", ["Remote"]),
         ("hispanic_ethnicity", "select", "No"), ("race", "select", "Asian"),
         ("candidate-location", "select_async", "Springfield, Illinois")]
    return [{"field_id": i, "label": i, "type": t, "value": v, "source": "profile"} for i, t, v in f]


def _cli(root: Path, tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), "apply", "fill", *args],
                          capture_output=True, text=True, env=ready_env(root, home), timeout=120)


def test_fill_refuses_without_plan(temp_root: Path, tmp_path: Path):
    (temp_root / "data" / "jobs" / "j-1").mkdir(parents=True)
    r = _cli(temp_root, tmp_path, "j-1")
    assert r.returncode == 1 and "apply plan" in r.stderr


@pytest.mark.parametrize("extra,code,msg", [({"blocked": ["SSN"]}, 3, "blocked"), ({}, 2, "unanswered")])
def test_fill_refuses_bad_plan(temp_root: Path, tmp_path: Path, extra, code, msg):
    jd = temp_root / "data" / "jobs" / "j-1"
    jd.mkdir(parents=True)
    fields = [{"field_id": "q", "label": "Sponsorship?", "type": "select", "value": None, "source": "pause:legal"}]
    (jd / "fill_plan.json").write_text(json.dumps({"job_id": "j-1", "board": "b", "ats_job_id": "1",
                                                   "fields": [] if extra else fields, **extra}))
    r = _cli(temp_root, tmp_path, "j-1")
    assert r.returncode == code and msg in r.stderr
    assert not (jd / "fill_summary.json").exists()


@pytest.fixture
def server():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(GH))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    handler.log_message = lambda *a: None
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _run(server: str, tmp_path: Path, page_name: str, fields: list[dict]) -> tuple[dict, str]:
    sync_api = pytest.importorskip("playwright.sync_api")
    from careeros.apply import gh_fill

    plan = {"job_id": "j-1", "board": "b", "ats_job_id": "1", "fields": fields}
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except sync_api.Error as e:
            pytest.skip(f"no playwright browser installed: {e}")
        page = browser.new_page()
        summary = gh_fill.fill(plan, page, tmp_path, url=f"{server}/{page_name}")
        title = page.title()
        browser.close()
    return summary, title


@pytest.mark.parametrize("page_name", ["job_app.html", "host.html"])  # direct form, and embedded in an iframe
def test_fill_fixture_form(server: str, tmp_path: Path, page_name: str):
    summary, title = _run(server, tmp_path, page_name, _fields(tmp_path))
    assert summary["failed"] == [] and summary["filled"] == 8, summary
    assert summary["fill_s"] >= 0 and title != "SUBMITTED"  # staged only, never submitted
    assert json.loads((tmp_path / "fill_summary.json").read_text()) == summary
    assert (tmp_path / "screenshots" / "fill.png").exists()


def test_fill_skips_race_unless_not_hispanic(server: str, tmp_path: Path):
    fields = [f for f in _fields(tmp_path) if f["field_id"] in ("hispanic_ethnicity", "race")]
    fields[0]["value"] = "Decline To Self Identify"  # race stays hidden: skip it, don't time out on it
    summary, _ = _run(server, tmp_path, "job_app.html", fields)
    assert summary["filled"] == 1 and summary["failed"] == [] and summary["skipped"] == ["race"], summary


def test_fill_maps_degree_to_fixed_label(server: str, tmp_path: Path):
    fields = [{"field_id": "degree--0", "label": "Degree", "type": "select_async",
               "value": "Bachelor of Engineering, Mechanical", "source": "profile"}]
    summary, _ = _run(server, tmp_path, "job_app.html", fields)  # no exact option: falls back to "Bachelor's Degree"
    assert summary["filled"] == 1 and summary["failed"] == [], summary
