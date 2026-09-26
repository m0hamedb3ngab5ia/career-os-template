"""Ghost-job detection: stale, reposted, not on the company's own site, hiring freeze / layoffs."""
from __future__ import annotations

from datetime import date

import pytest

from careeros.models import Posting
from careeros.safety.ghost import check_ghost, ghost_settings, history_key, load_signals

pytestmark = pytest.mark.unit

TODAY = date(2026, 9, 25)


def _p(**kw) -> Posting:
    base = dict(company="Nimbus", title="Software Engineer", location="New York, NY", ats="greenhouse",
                ats_job_id="1", url="https://boards.greenhouse.io/nimbus/jobs/1", posted_at="2026-09-20T10:00:00Z")
    base.update(kw)
    return Posting(**base)


def _codes(flags, severity=None):
    return {f.code for f in flags if severity is None or f.severity == severity}


def test_defaults(example_settings):
    g = ghost_settings(example_settings)
    assert (g["stale_flag_days"], g["stale_skip_days"], g["repost_flag_count"]) == (30, 45, 3)


def test_fresh_posting_is_clean(example_settings):
    assert check_ghost(_p(), None, {}, example_settings, today=TODAY) == []


@pytest.mark.parametrize("posted,sev", [("2026-08-20", "soft"), ("2026-08-10", "hard"), ("2026-06-01", "hard")])
def test_stale(example_settings, posted, sev):
    flags = check_ghost(_p(posted_at=posted), None, {}, example_settings, today=TODAY)
    assert _codes(flags, sev) == {"ghost_stale"}


def test_age_uses_earliest_of_posted_and_history(example_settings):
    hist = {"first_seen": "2026-07-01T00:00:00+00:00", "posted_at_min": None, "ats_job_ids": ["1"]}
    assert _codes(check_ghost(_p(), hist, {}, example_settings, today=TODAY), "hard") == {"ghost_stale"}


def test_no_date_at_all_is_not_stale(example_settings):
    assert check_ghost(_p(posted_at=None), None, {}, example_settings, today=TODAY) == []


def test_reposted(example_settings):
    hist = {"first_seen": "2026-09-10T00:00:00+00:00", "posted_at_min": "2026-09-10",
            "ats_job_ids": ["1", "2", "3"], "sightings": ["2026-07-01", "2026-08-01", "2026-09-10"]}
    assert _codes(check_ghost(_p(), hist, {}, example_settings, today=TODAY)) == {"ghost_reposted"}


def test_old_reposts_outside_window_do_not_count(example_settings):
    hist = {"first_seen": "2026-09-10T00:00:00+00:00", "ats_job_ids": ["1", "2", "3"],
            "sightings": ["2025-01-01", "2025-02-01", "2026-09-10"]}
    assert "ghost_reposted" not in _codes(check_ghost(_p(), hist, {}, example_settings, today=TODAY))


def test_aggregator_posting_not_linked_to_company_site(example_settings):
    p = _p(raw={"source": "jobright"})
    assert _codes(check_ghost(p, None, {}, example_settings, today=TODAY), "soft") == {"ghost_unlinked"}
    p2 = _p(raw={"source": "jobright", "resolved_from": "https://jobright.ai/j/1"})
    assert check_ghost(p2, None, {}, example_settings, today=TODAY) == []


def test_freeze_is_hard_and_layoffs_soft(example_settings):
    freeze = {"nimbus": {"kind": "freeze", "date": "2026-07-01", "source_url": "https://news.example/x"}}
    lay = {"nimbus": {"kind": "layoffs", "date": "2026-06-01", "source_url": "https://news.example/y"}}
    old = {"nimbus": {"kind": "layoffs", "date": "2025-01-01", "source_url": "https://news.example/z"}}
    assert _codes(check_ghost(_p(), None, freeze, example_settings, today=TODAY), "hard") == {"ghost_freeze"}
    assert _codes(check_ghost(_p(), None, lay, example_settings, today=TODAY), "soft") == {"ghost_layoffs"}
    assert check_ghost(_p(), None, old, example_settings, today=TODAY) == []


def test_dream_company_is_never_hard_skipped(example_settings):
    freeze = {"stripe": {"kind": "freeze", "date": "2026-09-01", "source_url": "u"}}
    flags = check_ghost(_p(company="Stripe", posted_at="2026-05-01"), None, freeze, example_settings, today=TODAY)
    assert _codes(flags) == {"ghost_stale", "ghost_freeze"} and not _codes(flags, "hard")


@pytest.mark.parametrize("a,b", [
    (("Software Engineer, New Grad (2026)", "New York, NY"), ("Software Engineer - New Grad", "New York, NY")),
    (("Software Engineer II R-12345", "NYC"), ("Software Engineer II", "NYC")),
])
def test_history_key_normalizes(a, b):
    assert history_key("Acme", *a) == history_key("Acme, Inc.", *b)


def test_history_key_distinguishes_roles():
    assert history_key("Acme", "Software Engineer", "NY") != history_key("Acme", "Data Engineer", "NY")


def test_load_signals_merges_config_over_data(example_settings, tmp_path):
    import json

    f = tmp_path / "company_signals.json"
    f.write_text(json.dumps({"nimbus": {"kind": "layoffs", "date": "2026-06-01", "source_url": "a"}}))
    example_settings.companies["hiring_signals"] = [{"company": "Nimbus", "kind": "none", "date": "2026-09-01"}]
    assert load_signals(example_settings, f)["nimbus"]["kind"] == "none"
