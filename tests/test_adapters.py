import pytest
from conftest import load_fixture

from careeros.scout.ashby import AshbyAdapter
from careeros.scout.base import html_to_text
from careeros.scout.greenhouse import GreenhouseAdapter
from careeros.scout.lever import LeverAdapter

pytestmark = pytest.mark.unit

BOARD = {"company": "Acme", "slug": "acme"}


def test_html_to_text_strips_and_unescapes():
    out = html_to_text("&lt;p&gt;Hi &amp; bye&lt;/p&gt;&lt;ul&gt;&lt;li&gt;a&lt;/li&gt;&lt;/ul&gt;")
    assert [l for l in out.split("\n") if l] == ["Hi & bye", "a"]
    assert "<" not in out
    assert html_to_text("<p>x</p><p>y</p>").split() == ["x", "y"]
    assert html_to_text(None) == ""


def test_greenhouse_parse():
    ps = GreenhouseAdapter().parse(load_fixture("greenhouse.json"), BOARD)
    assert len(ps) == 2
    p = ps[0]
    assert p.ats == "greenhouse" and p.ats_job_id == "4011001" and p.source_slug == "acme"
    assert p.title == "Software Engineer, Backend" and p.location == "New York, NY"
    assert p.url == "https://boards.greenhouse.io/acme/jobs/4011001"
    assert "payments infra" in p.description_text and "<" not in p.description_text
    assert "Python" in p.description_text
    assert p.departments == ["Engineering"]
    assert p.remote is False
    assert ps[1].remote is True
    assert p.raw["metadata"]["Employment Type"] == "Full-time"
    assert len(p.job_id) == 12


def test_lever_parse():
    ps = LeverAdapter().parse(load_fixture("lever.json"), BOARD)
    assert len(ps) == 2
    p = ps[0]
    assert p.ats == "lever" and p.ats_job_id == "a1b2c3d4-0000-4000-8000-000000000001"
    assert p.title == "Data Engineer"
    assert p.location == "New York, San Francisco"
    assert p.remote is False
    assert p.salary_min == 140000 and p.salary_max == 180000 and p.salary_currency == "USD"
    assert p.departments == ["Engineering", "Data Platform"]
    assert "Own our ETL pipelines." in p.description_text and "Requirements" in p.description_text
    assert "SQL" in p.description_text
    assert p.posted_at.startswith("2025-09-16")
    assert p.apply_url.endswith("/apply")
    assert ps[1].raw["country"] == "DE" and ps[1].location == "Berlin"


def test_ashby_parse():
    ps = AshbyAdapter().parse(load_fixture("ashby.json"), BOARD)
    assert len(ps) == 1
    p = ps[0]
    assert p.ats == "ashby" and p.ats_job_id == "7f0e0000-1111-2222-3333-444444444444"
    assert p.title == "Full Stack Engineer"
    assert p.location == "New York, San Francisco"
    assert p.remote is False
    assert p.salary_min == 150000 and p.salary_max == 200000 and p.salary_currency == "USD"
    assert p.departments == ["Engineering", "Product Engineering"]
    assert p.description_text.startswith("About")
    assert p.description_html.startswith("<h2>")
    assert p.apply_url.endswith("/application")
    assert p.raw["address"]["postalAddress"]["addressCountry"] == "United States"


# --- salary / location / remote parsing edge cases ---------------------------

def test_greenhouse_no_salary_empty_location_missing_id():
    data = {"jobs": [{"title": "  Backend Engineer ", "location": None, "absolute_url": "https://x/1"}]}
    (p,) = GreenhouseAdapter().parse(data, BOARD)
    assert p.title == "Backend Engineer"
    assert p.location == ""
    assert p.salary_min is None and p.salary_max is None and p.salary_currency is None
    assert p.ats_job_id is None and p.job_id  # falls back to url-based id
    assert GreenhouseAdapter().parse({}, BOARD) == []


def test_greenhouse_remote_from_title():
    data = {"jobs": [{"id": 1, "title": "Software Engineer (Remote)", "location": {"name": "United States"}}]}
    assert GreenhouseAdapter().parse(data, BOARD)[0].remote is True


@pytest.mark.parametrize("workplace,loc,remote", [
    ("remote", "New York", True),
    ("onsite", "Remote - US", False),
    ("on-site", "", False),
    ("hybrid", "New York", False),
    ("", "Remote - US", True),
    ("", "", None),
])
def test_lever_remote(workplace, loc, remote):
    data = [{"id": "x", "text": "SWE", "categories": {"location": loc}, "workplaceType": workplace}]
    assert LeverAdapter().parse(data, BOARD)[0].remote is remote


def test_lever_single_location_no_salary_bad_timestamp():
    data = [{"id": "x", "text": "SWE", "categories": {"location": "Boston"}, "allLocations": ["Boston"],
             "createdAt": "not-a-number", "salaryRange": None}]
    (p,) = LeverAdapter().parse(data, BOARD)
    assert p.location == "Boston"
    assert p.salary_min is None and p.salary_currency is None
    assert p.posted_at is None
    assert LeverAdapter().parse(None, BOARD) == []


def test_lever_partial_salary():
    data = [{"id": "x", "text": "SWE", "salaryRange": {"min": 125000, "currency": "USD"}}]
    (p,) = LeverAdapter().parse(data, BOARD)
    assert p.salary_min == 125000 and p.salary_max is None and p.salary_currency == "USD"


def _ashby(**kw):
    j = {"id": "a1", "title": "SWE", "location": "New York", "jobUrl": "https://x/a1"}
    j.update(kw)
    return {"jobs": [j]}


def test_ashby_salary_from_tiers_when_no_summary():
    comp = {"summaryComponents": [{"compensationType": "EquityPercentage", "minValue": 0.1}],
            "compensationTiers": [{"components": [
                {"compensationType": "Bonus", "minValue": 5},
                {"compensationType": "Salary", "minValue": 130000, "maxValue": 160000, "currencyCode": "EUR"}]}]}
    (p,) = AshbyAdapter().parse(_ashby(compensation=comp), BOARD)
    assert (p.salary_min, p.salary_max, p.salary_currency) == (130000, 160000, "EUR")


def test_ashby_no_salary_component():
    comp = {"summaryComponents": [{"compensationType": "Equity"}], "compensationTierSummary": "$1 equity"}
    (p,) = AshbyAdapter().parse(_ashby(compensation=comp), BOARD)
    assert p.salary_min is None and p.salary_max is None and p.salary_currency is None
    assert p.raw["compensationTierSummary"] == "$1 equity"


@pytest.mark.parametrize("is_remote,workplace,loc,remote", [
    (True, "OnSite", "New York", True),
    (False, "Remote", "Remote", False),   # explicit isRemote wins
    (None, "Remote", "New York", True),
    (None, None, "New York", False),
])
def test_ashby_remote(is_remote, workplace, loc, remote):
    (p,) = AshbyAdapter().parse(_ashby(isRemote=is_remote, workplaceType=workplace, location=loc), BOARD)
    assert p.remote is remote


def test_ashby_secondary_locations_and_text_fallback():
    (p,) = AshbyAdapter().parse(_ashby(secondaryLocations=[{"location": "Boston"}, {"location": None}],
                                       descriptionHtml="<p>Hello <b>there</b></p>"), BOARD)
    assert p.location == "New York, Boston"
    assert p.description_text == "Hello there"
    assert p.apply_url == "https://x/a1"
    assert AshbyAdapter().parse(None, BOARD) == []


# --- get_json ------------------------------------------------------------------

class _Resp:
    def __init__(self, status, payload=None, bad_json=False):
        self.status_code = status
        self._payload = payload
        self._bad = bad_json

    def raise_for_status(self):
        import requests

        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        if self._bad:
            raise ValueError("not json")
        return self._payload


def _patch_get(monkeypatch, responses):
    import careeros.scout.base as base

    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, params, headers))
        return responses.pop(0)

    monkeypatch.setattr(base.requests, "get", fake_get)
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    return calls


def test_get_json_404_is_board_not_found(monkeypatch):
    from careeros.scout.base import BoardNotFound, get_json

    calls = _patch_get(monkeypatch, [_Resp(404)])
    with pytest.raises(BoardNotFound):
        get_json("https://x/404")
    assert len(calls) == 1  # 404 is never retried


def test_get_json_retries_then_succeeds(monkeypatch):
    from careeros.scout.base import USER_AGENT, get_json

    calls = _patch_get(monkeypatch, [_Resp(503), _Resp(200, {"ok": 1})])
    assert get_json("https://x", params={"a": "b"}) == {"ok": 1}
    assert len(calls) == 2 and calls[0][1] == {"a": "b"} and calls[0][2]["User-Agent"] == USER_AGENT


@pytest.mark.parametrize("resps", [[_Resp(500), _Resp(500)], [_Resp(200, bad_json=True), _Resp(200, bad_json=True)]])
def test_get_json_gives_up_with_fetch_error(monkeypatch, resps):
    from careeros.scout.base import FetchError, get_json

    _patch_get(monkeypatch, list(resps))
    with pytest.raises(FetchError):
        get_json("https://x")


@pytest.mark.parametrize("fields,out", [(("Remote - US",), True), (("NYC", None), False), ((None, ""), None)])
def test_guess_remote(fields, out):
    from careeros.scout.base import guess_remote

    assert guess_remote(*fields) is out


def test_lever_all_locations_read_from_categories():
    data = [{"id": "m", "text": "SWE", "hostedUrl": "https://x/m",
             "categories": {"location": "New York", "allLocations": ["New York", "Toronto"]}}]
    assert LeverAdapter().parse(data, BOARD)[0].location == "New York, Toronto"


def test_lever_secondary_location_in_blocked_country_is_filtered(settings):
    from careeros.scout import Prefilter

    settings.targets.setdefault("location", {})["blocked_countries"] = ["CA"]
    data = [{"id": "m", "text": "Software Engineer", "hostedUrl": "https://x/m",
             "categories": {"location": "New York", "allLocations": ["New York", "Toronto"]}}]
    p = LeverAdapter().parse(data, BOARD)[0]
    assert Prefilter(settings).location_blocked(p)


def test_lever_remote_secondary_location_without_workplace_type():
    data = [{"id": "r", "text": "SWE", "hostedUrl": "https://x/r",
             "categories": {"location": "New York", "allLocations": ["New York", "Remote"]}}]
    p = LeverAdapter().parse(data, BOARD)[0]
    assert p.location == "New York, Remote" and p.remote is True
