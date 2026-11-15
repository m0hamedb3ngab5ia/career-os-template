import json

import pytest

from careeros.scout import handshake as hs
from careeros.scout.base import FetchError
from careeros.scout.handshake import HandshakeAdapter

pytestmark = pytest.mark.unit

BOARD = {"company": "Handshake", "ats": "handshake", "slug": "handshake"}


def _edge(jid, title, employer="Acme Corp", job_type="JOB", emp="FULL_TIME", salary=None, remote=False, hybrid=False):
    return {"node": {"job": {
        "id": jid, "title": title, "createdAt": "2026-11-10T09:00:00-05:00",
        "expirationDate": "2026-12-01T23:59:59-05:00",
        "jobType": {"behaviorIdentifier": job_type}, "employmentType": {"behaviorIdentifier": emp},
        "remote": remote, "hybrid": hybrid, "onSite": not (remote or hybrid),
        "locations": [{"name": "New York, NY", "country": "United States"}, {"name": "Remote", "country": None}],
        "salaryRange": salary, "employer": {"id": "9", "name": employer},
        "description": "<p>Build <b>APIs</b>.</p>",
    }}}


def test_parse_maps_employer_salary_and_skips_non_fulltime_jobs():
    data = {"data": {"jobSearch": {"edges": [
        _edge("1", "Software Engineer", salary={"min": 12500000, "max": 15000000, "currency": "USD",
                                                 "paySchedule": {"behaviorIdentifier": "ANNUAL_SALARY"}}, hybrid=True),
        _edge("2", "SWE Intern", job_type="INTERNSHIP"),
        _edge("3", "Part-time Engineer", emp="PART_TIME"),
        _edge("4", "Backend Engineer", salary={"min": 4000, "max": 5000, "currency": "USD",
                                                "paySchedule": {"behaviorIdentifier": "HOURLY_WAGE"}}),
    ]}}}
    ps = HandshakeAdapter().parse(data, BOARD)
    assert [p.title for p in ps] == ["Software Engineer", "Backend Engineer"]
    p = ps[0]
    assert p.company == "Acme Corp" and p.ats == "handshake" and p.ats_job_id == "1"
    assert p.url == "https://app.joinhandshake.com/job-search/1"
    assert (p.salary_min, p.salary_max, p.salary_currency) == (125000, 150000, "USD")
    assert p.location == "New York, NY; Remote" and p.raw["workplaceType"] == "hybrid"
    assert p.posted_at.startswith("2026-11-10") and "Build APIs." in p.description_text
    assert p.closes_at == "2026-12-01"  # Handshake expirationDate = its "Apply by" date
    assert ps[1].salary_min is None  # hourly pay is not a base salary


def test_parse_dedupes_jobs_seen_on_several_pages():
    data = {"data": {"jobSearch": {"edges": [_edge("1", "Software Engineer"), _edge("1", "Software Engineer")]}}}
    assert len(HandshakeAdapter().parse(data, BOARD)) == 1


class FakePage:
    """Scripted stand-in for a Playwright page: `url` after goto, one evaluate() result per call."""

    def __init__(self, results, url="https://app.joinhandshake.com/explore"):
        self.results, self.url, self.bodies = list(results), url, []

    def goto(self, url, **_):
        pass

    def evaluate(self, _js, body):
        self.bodies.append(body)
        return self.results.pop(0)


def _ok(n):
    return {"status": 200, "text": json.dumps({"data": {"jobSearch": {"edges": [_edge(str(i), "SWE") for i in range(n)]}}})}


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch):
    monkeypatch.setattr(hs, "PAUSE_S", 0)


def test_search_pages_until_a_short_page():
    page = FakePage([_ok(25), _ok(3)])
    edges = hs.search(page, ["software engineer"], pages=5)
    assert len(edges) == 28
    assert [b["variables"]["after"] for b in page.bodies] == ["MA==", "MjU="]
    assert page.bodies[0]["variables"]["input"]["filter"]["query"] == "software engineer"


@pytest.mark.parametrize("page", [FakePage([], url="https://app.joinhandshake.com/access"),
                                  FakePage([{"status": 403, "text": ""}])])
def test_search_signed_out_raises(page):
    with pytest.raises(FetchError, match="not signed in"):
        hs.search(page, ["software engineer"], pages=1)


def test_search_graphql_errors_raise():
    page = FakePage([{"status": 200, "text": json.dumps({"errors": [{"message": "bad sort"}]})}])
    with pytest.raises(FetchError, match="^handshake graphql"):
        hs.search(page, ["software engineer"], pages=1)
