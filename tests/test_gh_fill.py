"""Pure parts of the Greenhouse filler: plan gate, URLs, lazy Playwright import."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from careeros.apply import gh_fill

pytestmark = pytest.mark.unit


def _plan(**kw):
    fields = [{"field_id": "email", "label": "Email", "type": "text", "value": "a@example.com", "source": "profile"},
              {"field_id": "resume", "label": "Resume", "type": "file", "value": None, "source": None}]
    return {"job_id": "x-1", "board": "acme", "ats_job_id": "123", "fields": fields, **kw}


def test_plan_problems_ok():
    assert gh_fill.plan_problems(_plan()) == []


def test_plan_problems_blocked():
    assert gh_fill.plan_problems(_plan(blocked=["SSN"])) == ["blocked (sensitive field): SSN"]


def test_plan_problems_unanswered_pause():
    p = _plan()
    p["fields"].append({"field_id": "q9", "label": "Need sponsorship?", "type": "select", "value": None,
                        "source": "pause:legal"})
    assert gh_fill.plan_problems(p) == ["unanswered (pause:legal): Need sponsorship?"]


def test_job_url():
    assert gh_fill.job_url(_plan()) == "https://job-boards.greenhouse.io/embed/job_app?for=acme&token=123"


def test_missing_playwright_is_friendly(monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    with pytest.raises(gh_fill.MissingPlaywright, match=r"pip install -e '\.\[fast-apply\]'"):
        gh_fill.sync_playwright()


def test_read_back_matches():
    assert gh_fill.matches("select", "Yes", "Yes")
    assert not gh_fill.matches("select", "Yes", "No")
    assert gh_fill.matches("select_async", "Springfield", "Springfield, Illinois, United States")
    assert gh_fill.matches("select", "United States", "+1", field_id="country")  # phone widget shows dial code
    assert gh_fill.matches("multiselect", ["A", "B"], "AB")


def test_degree_key():
    assert gh_fill.degree_key("Bachelor of Engineering, Mechanical") == "bachelor"
    assert gh_fill.degree_key("Master of Science") == "master"
    assert gh_fill.degree_key("PhD, Physics") == gh_fill.degree_key("Ph.D.") == "philosophy"
    assert gh_fill.degree_key("Doctor of Philosophy") == "philosophy"
    assert gh_fill.degree_key("Associate of Arts") == "associate"
    assert gh_fill.degree_key("High School Diploma") == "high school"
    assert gh_fill.degree_key("BS Computer Science") is None


def test_degree_read_back_by_keyword():
    assert gh_fill.matches("select_async", "Bachelor of Engineering, X", "Bachelor's Degree", field_id="degree--0")
    assert not gh_fill.matches("select_async", "Bachelor of Engineering, X", "Master's Degree", field_id="degree--0")
    assert not gh_fill.matches("select_async", "Bachelor of Engineering, X", "Bachelor's Degree", field_id="school--0")


def test_run_closes_its_tab_when_fill_raises(monkeypatch, tmp_path):
    from unittest.mock import MagicMock
    p = MagicMock()
    page = p.chromium.connect_over_cdp.return_value.contexts[0].new_page.return_value
    monkeypatch.setattr(gh_fill, "sync_playwright", lambda: MagicMock(__enter__=lambda s: p))
    monkeypatch.setattr(gh_fill, "fill", MagicMock(side_effect=RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        gh_fill.run(_plan(), tmp_path, cdp="http://127.0.0.1:1", profile_dir=tmp_path)
    page.close.assert_called_once()


def test_fill_survives_screenshot_timeout(tmp_path):
    """The proof screenshot is best-effort: a timeout there must not fail an already filled form."""
    page = MagicMock()
    page.locator.return_value.count.return_value = 0
    page.screenshot.side_effect = RuntimeError("Page.screenshot: Timeout 10000ms exceeded.")
    summary = gh_fill.fill({"fields": []}, page, tmp_path, url="http://x")
    assert summary["filled"] == 0 and (tmp_path / "fill_summary.json").is_file()


def test_plan_problems_required_needs_input_blocks():
    """REQ-106: a required field with no answer blocks the fill; an optional or skipped one does not."""
    p = _plan()
    p["fields"] += [{"field_id": "q1", "label": "Notice period", "type": "text", "value": None, "source": "unanswered",
                     "required": True},
                    {"field_id": "q2", "label": "Hobbies", "type": "text", "value": None, "source": "unanswered",
                     "required": False, "skipped": True}]
    assert gh_fill.plan_problems(p) == ["needs input (required): Notice period"]
    p["fields"][2]["value"] = "4 weeks"
    assert gh_fill.plan_problems(p) == []
