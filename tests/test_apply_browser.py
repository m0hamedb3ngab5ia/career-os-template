"""The apply browser's liveness / focus / launch over CDP HTTP, with a fake endpoint (no browser, no network)."""
from __future__ import annotations

import json
import sys

import pytest

from careeros.apply import browser

pytestmark = pytest.mark.unit
CDP = "http://127.0.0.1:9223"


def fake(tabs_list, calls=None):
    def get(url):
        if calls is not None:
            calls.append(url)
        if tabs_list is None:
            raise OSError("connection refused")
        if "/json/activate/" in url:
            raise ValueError("Target activated")  # plain text, not JSON
        return tabs_list
    return get


def test_never_filled_is_none(tmp_path):
    assert browser.status(tmp_path, CDP, fake([])) == {"tab": "none", "submitted": False, "can_fill": False}


def test_live_tab_is_open_and_focusable(tmp_path):
    (tmp_path / "fill_plan.json").write_text("{}")
    browser.save_record(tmp_path, tab_id="T1", url="https://job-boards.example/embed", cdp=CDP)
    calls: list[str] = []
    get = fake([{"id": "T1", "type": "page", "url": "https://job-boards.example/embed"}], calls)
    assert browser.status(tmp_path, CDP, get) == {"tab": "open", "submitted": False, "can_fill": True}
    assert browser.activate(tmp_path, CDP, get) is True and calls[-1] == f"{CDP}/json/activate/T1"


@pytest.mark.parametrize("tabs_list", [None, [], [{"id": "OTHER", "type": "page", "url": "x"}]])
def test_dead_tab_or_browser_needs_refill(tmp_path, tabs_list):
    browser.save_record(tmp_path, tab_id="T1", url="u", cdp=CDP)
    assert browser.status(tmp_path, CDP, fake(tabs_list))["tab"] == "needs_refill"
    assert browser.activate(tmp_path, CDP, fake(tabs_list)) is False


def test_confirmation_page_counts_as_submitted(tmp_path):
    browser.save_record(tmp_path, tab_id="T1", url="u", cdp=CDP)
    get = fake([{"id": "T1", "type": "page", "url": "https://job-boards.example/ledgerline/jobs/1/confirmation?x=1"}])
    assert browser.status(tmp_path, CDP, get)["submitted"] is True
    assert not browser.is_confirmation("https://job-boards.example/ledgerline/jobs/1?q=/confirmation")


def test_record_round_trip(tmp_path):
    browser.save_record(tmp_path, tab_id="T9", url="u", cdp=CDP)
    rec = json.loads((tmp_path / "application.json").read_text())
    assert rec["tab_id"] == "T9" and rec["cdp"] == CDP and browser.record(tmp_path)["url"] == "u"


def test_ensure_launches_detached_only_when_nothing_answers(tmp_path):
    launched: list[dict] = []
    opened: list[str] = []
    browser.ensure(CDP, tmp_path, "chrome", get=fake([]), popen=lambda *a, **k: launched.append(k), put=opened.append)
    assert launched == [] and opened == [f"{CDP}/json/new?about:blank"]  # alive, no window (last tab closed)
    browser.ensure(CDP, tmp_path, "chrome", get=fake([{"id": "T", "type": "page"}]), popen=launched.append,
                   put=opened.append)
    assert launched == [] and len(opened) == 1
    state = {"up": False}

    def get(url):
        if not state["up"]:
            raise OSError("refused")
        return []

    def popen(argv, **k):
        launched.append({"argv": argv, **k})
        state["up"] = True

    browser.ensure(CDP, tmp_path, "chrome", get=get, popen=popen)
    assert launched[0]["start_new_session"] is True and "--remote-debugging-port=9223" in launched[0]["argv"]


def test_ensure_times_out(tmp_path):
    with pytest.raises(RuntimeError, match="did not start"):
        browser.ensure(CDP, tmp_path, "chrome", get=fake(None), popen=lambda *a, **k: None, wait_s=0.3)


def test_cdp_url_default_and_override():
    class S:
        paths = {"apply_cdp": "http://127.0.0.1:9333"}
    assert browser.cdp_url(S()) == "http://127.0.0.1:9333"
    assert browser.cdp_url(object()) == browser.DEFAULT_CDP


def test_fill_failure_from_log(tmp_path):
    from careeros.apply import browser

    assert browser.fill_failure(tmp_path) is None  # never ran
    log = tmp_path / "application.log"
    log.write_text("filling...\n")
    assert browser.fill_failure(tmp_path) is None  # still running
    log.write_text(f"ok\n{browser.FILL_EXIT}0\n")
    assert browser.fill_failure(tmp_path) is None  # succeeded
    log.write_text(f"{browser.STAGED} (15 filled, 5 failed; x)\n{{\n}}\n{browser.FILL_EXIT}1\n")
    assert browser.fill_failure(tmp_path) is None  # staged; some fields left for the user
    log.write_text(f"Traceback...\nplaywright is not installed: pip install x\n{browser.FILL_EXIT}1\n")
    f = browser.fill_failure(tmp_path)
    assert f["error"] == "playwright is not installed: pip install x" and "Traceback" in f["log"]
    assert browser.status(tmp_path, browser.DEFAULT_CDP)["fill_error"] == f["error"]


def test_preflight_missing_playwright_and_chromium(monkeypatch, tmp_path):
    from careeros.apply import gh_fill

    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    with pytest.raises(gh_fill.MissingPlaywright, match="fast-apply"):
        gh_fill.preflight()

    class P:
        def __enter__(self):
            return type("pw", (), {"chromium": type("c", (), {"executable_path": str(tmp_path / "nope")})})

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(gh_fill, "sync_playwright", lambda: P())
    with pytest.raises(gh_fill.MissingPlaywright, match="playwright install chromium"):
        gh_fill.preflight()
