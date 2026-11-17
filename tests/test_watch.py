"""REQ-159 target watch + urgent, REQ-160 season windows. Fake sender: no network."""
from __future__ import annotations

from datetime import date

import pytest

from careeros import notify
from careeros.models import Posting, Score
from careeros.runs import policy
from careeros.store import Store
from careeros.tracker import Tracker
from careeros.watch import scan_watch

pytestmark = pytest.mark.unit


def _scored(s, n, company, fit, fails=()):
    p = Posting(company=company, title=f"Engineer {n}", ats="greenhouse", ats_job_id=str(n),
                description_text="x", url=f"https://example.com/{n}")
    st = Store(s)
    st.save_posting(p)
    st.save_score(Score(job_id=p.job_id, category="swe", fit=fit, hard_filter_fails=list(fails)))
    return p


@pytest.fixture
def env(settings):
    Tracker(settings=settings).init()
    settings.companies["dream_list"] = ["Initech"]
    settings.companies["boards"] = [{"company": "Globex", "ats": "greenhouse", "slug": "g", "watch": True}]
    assert scan_watch(settings) == []  # first run only sets the baseline
    return settings


def test_first_run_baselines_existing_jobs_without_alerts(settings):
    Tracker(settings=settings).init()
    settings.companies["dream_list"] = ["Initech"]
    _scored(settings, 1, "Initech", 95)
    sent = []
    assert scan_watch(settings, send=lambda *a: sent.append(a) or "sent") == []
    later = _scored(settings, 2, "Initech", 95)
    assert scan_watch(settings, send=lambda *a: sent.append(a) or "sent") == [later.job_id] and len(sent) == 1


def test_watch_urgent_once_per_job_and_only_high_fit_unfiltered(env):
    sent = []
    send = lambda s, key, subj, body: sent.append((key, subj, body)) or "sent"  # noqa: E731
    hi = _scored(env, 1, "Initech", 90)
    lo = _scored(env, 2, "Globex", 70)                    # watched via `watch: true`, below urgent fit
    _scored(env, 3, "Initech", 95, fails=["location"])     # hard-filtered
    _scored(env, 4, "Hooli", 99)                           # not watched
    assert scan_watch(env, send=send) == [hi.job_id, lo.job_id]
    assert scan_watch(env, send=send) == []
    assert [k for k, *_ in sent] == [f"watch:{hi.job_id}"]
    assert "apply as soon as possible" in sent[0][2].lower() and "https://example.com/1" in sent[0][2]
    items = [i for i in Tracker(settings=env).list_action_items() if i["Detail"] == "watch"]
    assert len(items) == 1 and items[0]["Priority"] == "H" and items[0]["JobID"] == hi.job_id


def test_digest_lists_new_at_targets_once(env):
    p = _scored(env, 1, "Globex", 70)
    scan_watch(env, send=lambda *a: "sent")
    body = notify.build_digest(env, date(2026, 11, 16))
    assert "New at your target companies" in body and "Engineer 1 @ Globex" in body and p.url in body
    env.pipeline["notify"] = {"enabled": True, "email": "me@example.com", "send_at": "00:00"}
    from datetime import datetime
    out = []
    notify.maybe_send_digest(env, datetime(2026, 11, 16, 9), sender=lambda c, sub, b, pw: out.append(b),
                             keychain=lambda e: "x")
    assert len(out) == 1 and notify.build_digest(env, date(2026, 11, 17)) is None or "Globex" not in notify.build_digest(env, date(2026, 11, 17))


WINDOWS = [
    {"name": "fall", "start": "08-01", "end": "10-31", "level": "peak", "advice": "apply fast"},
    {"name": "lull", "start": "12-01", "end": "12-31", "level": "low", "multiplier": 0.5, "advice": "network"},
    {"name": "q1", "start": "01-01", "end": "03-31", "level": "high", "advice": "budgets reset"},
]


def _t(season):
    return {"volume": {"max_applications_per_day": 10, "season_multiplier": season}}


def test_named_windows_set_cap_and_describe_season():
    t = _t(WINDOWS)
    assert policy.daily_cap(t, date(2026, 9, 5)) == 20 and policy.daily_cap(t, date(2026, 12, 5)) == 5
    assert policy.daily_cap(t, date(2026, 11, 5)) == 10     # no window: base
    s = policy.season_on(t, date(2026, 9, 5))
    assert s["name"] == "fall" and s["weekly_target"] == 140 and s["advice"] == "apply fast"
    assert policy.season_on(t, date(2026, 11, 5)) is None


def test_old_month_form_still_works_and_bad_window_rejected():
    assert policy.daily_cap(_t({"9": 2.0}), date(2026, 9, 1)) == 20
    assert policy.season_on(_t({"9": 2.0}), date(2026, 9, 1)) is None
    with pytest.raises(policy.ConfigError):
        policy.daily_cap(_t([{"name": "x", "start": "13-40", "end": "01-01"}]), date(2026, 9, 1))


def test_digest_heads_up_once_before_high_window(env):
    env.targets["volume"] = _t(WINDOWS)["volume"]
    d = date(2026, 12, 27)                                  # q1 starts 01-01, 5 days out
    assert "q1 starts 2027-01-01" in notify.build_digest(env, d)
    assert policy.upcoming_window(env.targets, date(2026, 12, 20)) is None   # 12 days out
    assert policy.upcoming_window(env.targets, date(2026, 11, 20)) is None   # lull is low, fall already running
    env.pipeline["notify"] = {"enabled": True, "email": "me@example.com", "send_at": "00:00"}
    from datetime import datetime
    notify.maybe_send_digest(env, datetime(2026, 12, 27, 9), sender=lambda *a: None, keychain=lambda e: "x")
    assert notify.build_digest(env, date(2026, 12, 28)) is None
