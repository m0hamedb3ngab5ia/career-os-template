"""Next-step rule order (REQ-122): setup -> find jobs -> pick jobs -> see progress -> start pipeline."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from careeros.ui.routers.next_step import pick  # noqa: E402

pytestmark = pytest.mark.unit

OPEN = [{"id": "master", "must": True, "done": False, "fix_link": "/profile#master"},
        {"id": "cv", "must": True, "done": False, "fix_link": "/profile#cv"}]
DONE = [{"id": "master", "must": True, "done": True, "fix_link": "/x"},
        {"id": "opt", "must": False, "done": False, "fix_link": "/y"}]


def test_open_must_have_finishes_setup_at_first_open_item():
    s = pick(OPEN, jobs=5, ticked=5, running_batch="b1")
    assert (s.key, s.label, s.href) == ("finish_setup", "Finish setup", "/profile#master")


def test_optional_open_item_does_not_block():
    assert pick(DONE, jobs=0, ticked=0, running_batch=None).key == "find_jobs"


def test_no_jobs_finds_jobs():
    s = pick(DONE, jobs=0, ticked=0, running_batch="b1")
    assert (s.key, s.label, s.href) == ("find_jobs", "Find jobs", None)


def test_no_ticked_jobs_picks_jobs():
    s = pick(DONE, jobs=12, ticked=0, running_batch="b1")
    assert (s.key, s.label, s.href) == ("pick_jobs", "Pick jobs", "/jobs")


def test_running_batch_sees_progress():
    s = pick(DONE, jobs=12, ticked=3, running_batch="b 1")
    assert (s.key, s.label, s.href) == ("see_progress", "See progress", "/pipeline/batch/b%201")


def test_else_start_pipeline():
    s = pick(DONE, jobs=12, ticked=3, running_batch=None)
    assert (s.key, s.label, s.href) == ("start_pipeline", "Start pipeline", "/jobs")
