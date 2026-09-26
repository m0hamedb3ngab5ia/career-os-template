"""Action Items view logic (careeros.ui.services.actions): due buckets and levels, tabs, grouping, sorting."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from careeros.ui.services import actions as svc

pytestmark = pytest.mark.unit

UTC = timezone.utc
NY = ZoneInfo("America/New_York")
# Thursday 2026-09-24, 11:00 in New York
NOW = datetime(2026, 9, 24, 15, 0, tzinfo=UTC)


def row(id: str, *, due: str | None = None, priority: str = "M", needs: str = "anytime", done: int = 0,
        created: str = "2026-09-20 10:00:00", done_date: str | None = None, **kw) -> dict:
    return {"id": id, "created": created, "job_id": kw.get("job_id"), "company": kw.get("company", f"Co {id}"),
            "role": "Engineer", "type": kw.get("type", "review"), "what": f"do {id}", "link": kw.get("link"),
            "priority": priority, "needs": needs, "done": done, "done_date": done_date, "due": due,
            "due_reason": kw.get("due_reason")}


@pytest.mark.parametrize("due,bucket,level", [
    (None, "nodate", "none"),
    ("2026-09-23T12:00:00-04:00", "overdue", "overdue"),
    ("2026-09-24T09:00:00-04:00", "overdue", "overdue"),        # earlier today: already past
    ("2026-09-24T18:00:00-04:00", "today", "soon"),
    ("2026-09-24", "today", "soon"),                            # a date alone means the end of that day
    ("2026-09-24T00:00:00", "today", "soon"),                   # an Excel date cell (naive 00:00) = that date
    ("2026-09-25T15:00:00-04:00", "tomorrow", "soon"),
    ("2026-09-26T10:00:00-04:00", "week", "soon"),              # within 48 h
    ("2026-09-27T10:00:00-04:00", "week", "later"),
    ("2026-10-01", "week", "later"),
    ("2026-10-02", "later", "later"),
    ("not a date", "nodate", "none"),
])
def test_bucket_and_level(due, bucket, level):
    assert svc.due_bucket(due, NOW, NY) == bucket
    assert svc.due_level(due, NOW, NY, soon_hours=48) == level


def test_soon_window_is_configurable():
    due = "2026-09-26T10:00:00-04:00"
    assert svc.due_level(due, NOW, NY, soon_hours=24) == "later"


ROWS = [
    row("late", due="2026-09-23", priority="L", needs="phone"),
    row("today_h", due="2026-09-24T18:00:00-04:00", priority="H", needs="laptop"),
    row("today_m", due="2026-09-24T17:00:00-04:00", priority="M", needs="laptop"),
    row("tmrw", due="2026-09-25T15:00:00-04:00", priority="H"),
    row("week", due="2026-09-28", priority="M"),
    row("nod_h", priority="H", created="2026-09-22 10:00:00"),
    row("nod_l", priority="L", created="2026-09-23 10:00:00"),
    row("done1", done=1, done_date="2026-09-23"),
    row("done2", done=1, done_date="2026-09-24"),
]


def ids(view: dict) -> list[list[str]]:
    return [[i["id"] for i in g["items"]] for g in view["groups"]]


def test_open_tab_groups_by_due_soonest_then_priority():
    v = svc.build_view(ROWS, tab="open", group="due", sort="soonest", now=NOW, tz=NY, soon_hours=48)
    assert [g["key"] for g in v["groups"]] == ["overdue", "today", "tomorrow", "week", "nodate"]
    assert ids(v) == [["late"], ["today_m", "today_h"], ["tmrw"], ["week"], ["nod_h", "nod_l"]]
    assert v["counts"] == {"open": 7, "today": 4, "done": 2}
    assert v["head"] == {"overdue": 1, "soon": 3}
    first = v["groups"][0]["items"][0]
    assert first["level"] == "overdue" and first["bucket"] == "overdue"


def test_today_tab_is_overdue_through_tomorrow():
    v = svc.build_view(ROWS, tab="today", group="due", sort="soonest", now=NOW, tz=NY, soon_hours=48)
    assert [g["key"] for g in v["groups"]] == ["overdue", "today", "tomorrow"]


def test_done_tab_newest_done_first():
    v = svc.build_view(ROWS, tab="done", group="due", sort="soonest", now=NOW, tz=NY, soon_hours=48)
    assert ids(v) == [["done2", "done1"]] and v["groups"][0]["key"] == "done"


def test_group_by_priority_and_needs():
    v = svc.build_view(ROWS, tab="open", group="priority", sort="soonest", now=NOW, tz=NY, soon_hours=48)
    assert [g["key"] for g in v["groups"]] == ["H", "M", "L"]
    assert ids(v)[0] == ["today_h", "tmrw", "nod_h"]
    v = svc.build_view(ROWS, tab="open", group="needs", sort="soonest", now=NOW, tz=NY, soon_hours=48)
    assert [g["key"] for g in v["groups"]] == ["laptop", "phone", "anytime"]


def test_sort_by_priority_and_newest():
    v = svc.build_view(ROWS, tab="open", group="due", sort="priority", now=NOW, tz=NY, soon_hours=48)
    assert ids(v)[1] == ["today_h", "today_m"]
    assert ids(v)[4] == ["nod_h", "nod_l"]
    v = svc.build_view(ROWS, tab="open", group="due", sort="newest", now=NOW, tz=NY, soon_hours=48)
    assert ids(v)[4] == ["nod_l", "nod_h"]


def test_unknown_priority_or_needs_still_listed():
    rows = [row("x", priority="Z", needs="boat")]
    v = svc.build_view(rows, tab="open", group="priority", sort="soonest", now=NOW, tz=NY, soon_hours=48)
    assert ids(v) == [["x"]] and v["groups"][0]["key"] == "Z"
    v = svc.build_view(rows, tab="open", group="needs", sort="soonest", now=NOW, tz=NY, soon_hours=48)
    assert ids(v) == [["x"]]


def test_empty_is_zero_not_invented():
    v = svc.build_view([], tab="open", group="due", sort="soonest", now=NOW, tz=NY, soon_hours=48)
    assert v["groups"] == [] and v["counts"] == {"open": 0, "today": 0, "done": 0}
    assert v["head"] == {"overdue": 0, "soon": 0}


@pytest.mark.parametrize("kw", [{"tab": "later"}, {"group": "colour"}, {"sort": "random"}])
def test_bad_params_raise_value_error(kw):
    args = {"tab": "open", "group": "due", "sort": "soonest", **kw}
    with pytest.raises(ValueError):
        svc.build_view(ROWS, now=NOW, tz=NY, soon_hours=48, **args)


def test_scam_items_offer_block_and_safe_only_with_a_job():
    rows = [row("s1", type="scam_suspected", job_id="j1"), row("s2", type="scam_suspected"), row("r", job_id="j2")]
    v = svc.build_view(rows, tab="open", group="due", sort="soonest", now=NOW, tz=NY, soon_hours=48)
    by = {i["id"]: i for g in v["groups"] for i in g["items"]}
    assert by["s1"]["scam_actions"] is True and by["s2"]["scam_actions"] is False and by["r"]["scam_actions"] is False


def test_resolve_tz():
    assert svc.resolve_tz("America/New_York") == NY
    assert svc.resolve_tz(None) is not None
    with pytest.raises(ValueError):
        svc.resolve_tz("Mars/Olympus")


@pytest.mark.parametrize("link,ok", [("", True), ("https://example.com/x", True), ("http://a.b", True),
                                     ("javascript:alert(1)", False), ("profile/master.yaml", False)])
def test_new_item_link_must_be_http(link, ok):
    body = {"what": "Call back", "type": "other", "needs": "phone", "priority": "M", "link": link}
    if ok:
        assert svc.validate_new_item(body)["link"] == link
    else:
        with pytest.raises(ValueError):
            svc.validate_new_item(body)


def test_new_item_validation():
    with pytest.raises(ValueError):
        svc.validate_new_item({"what": "  "})
    with pytest.raises(ValueError):
        svc.validate_new_item({"what": "x", "type": "nope"})
    with pytest.raises(ValueError):
        svc.validate_new_item({"what": "x", "due": "tomorrowish"})
    got = svc.validate_new_item({"what": " x ", "due": "2026-10-01", "due_reason": " posting closes "})
    assert got["what"] == "x" and got["due"] == "2026-10-01" and got["due_reason"] == "posting closes"
    assert got["type"] == "other" and got["needs"] == "anytime" and got["priority"] == "M"


def test_a_naive_midnight_due_is_date_only():
    from careeros.ui.services.actions import is_date_only
    assert is_date_only("2026-10-03")
    assert is_date_only("2026-10-03 00:00:00")
    assert is_date_only("2026-10-03T00:00")
    assert not is_date_only("2026-10-03T00:00:00Z")
    assert not is_date_only("2026-10-03T09:30:00")
    assert not is_date_only(None)
