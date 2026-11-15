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
