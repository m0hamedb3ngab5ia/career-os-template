"""Plan/fill dispatch on the posting's ATS."""
from __future__ import annotations

import pytest

from careeros.apply import gh_fill

pytestmark = pytest.mark.unit


def test_job_url_ashby_uses_apply_url():
    plan = {"ats": "ashby", "apply_url": "https://jobs.ashbyhq.com/acme/j1/application", "board": "acme",
            "ats_job_id": "j1", "fields": []}
    assert gh_fill.job_url(plan) == "https://jobs.ashbyhq.com/acme/j1/application"


def test_job_url_greenhouse_unchanged():
    plan = {"ats": "greenhouse", "board": "acme", "ats_job_id": "5", "fields": []}
    assert gh_fill.job_url(plan) == "https://job-boards.greenhouse.io/embed/job_app?for=acme&token=5"


def test_plan_problems_same_gate_for_ashby():
    plan = {"ats": "ashby", "fields": [{"field_id": "x", "label": "Salary expectations", "value": None,
                                        "source": "pause:salary", "type": "text"}]}
    assert gh_fill.plan_problems(plan) == ["unanswered (pause:salary): Salary expectations"]


def test_checkbox_group_with_one_string_value_checks_that_option():
    from unittest.mock import MagicMock

    from careeros.apply import ashby_fill

    root = MagicMock()
    w = root.locator.return_value
    assert ashby_fill.fill_one(root, {"field_id": "f", "type": "checkbox_group", "value": "Austin, Texas"})
    labels = {c.args[0] for c in w.get_by_label.call_args_list}
    assert labels == {"Austin, Texas"}  # never one letter at a time
