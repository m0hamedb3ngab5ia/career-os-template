import pytest
from careeros.models import Posting, TrackerRow, make_job_id

pytestmark = pytest.mark.unit


def test_job_id_stable_and_short():
    a = Posting(company="Acme", title="SWE", ats="greenhouse", ats_job_id="123", url="https://x/1")
    b = Posting(company="Acme", title="SWE renamed", ats="greenhouse", ats_job_id="123", url="https://x/other")
    assert a.job_id == b.job_id
    assert len(a.job_id) == 12
    assert a.job_id == make_job_id("greenhouse", "Acme", "123", None)


def test_job_id_falls_back_to_url_and_differs_by_ats():
    a = Posting(company="Acme", title="SWE", ats="lever", url="https://x/1")
    b = Posting(company="Acme", title="SWE", ats="lever", url="https://x/2")
    c = Posting(company="Acme", title="SWE", ats="ashby", url="https://x/1")
    assert a.job_id != b.job_id
    assert a.job_id != c.job_id
    assert a.job_id == make_job_id("lever", "Acme", None, "https://x/1")


def test_explicit_job_id_preserved_on_roundtrip():
    p = Posting(company="Acme", title="SWE", ats="ashby", ats_job_id="z")
    again = Posting.model_validate(p.model_dump())
    assert again.job_id == p.job_id


def test_tracker_row_from_posting():
    p = Posting(company="Acme", title="SWE", ats="ashby", ats_job_id="z", location="NYC", remote=True,
                salary_min=100000, salary_max=150000, salary_currency="USD", url="https://x")
    r = TrackerRow.from_posting(p)
    assert r.remote == "Y"
    assert r.salary == "100,000-150,000 USD"
    assert r.status is None


# --- validation ------------------------------------------------------------------

from pydantic import ValidationError  # noqa: E402

from careeros.models import ActionItem, QACheck, QAResult, Score  # noqa: E402


@pytest.mark.parametrize("kw", [{"fit": 101}, {"fit": -1}, {"tier": "D"}])
def test_score_rejects_out_of_range(kw):
    base = {"job_id": "j", "category": "swe_backend", "fit": 50}
    with pytest.raises(ValidationError):
        Score(**{**base, **kw})


def test_score_passes_and_qa_hard_fails():
    assert Score(job_id="j", category="c", fit=0).passes
    assert not Score(job_id="j", category="c", fit=100, hard_filter_fails=["location"]).passes
    r = QAResult(job_id="j", artifact="cover_letter", passed=False, checks=[
        QACheck(name="soft", kind="soft", passed=False), QACheck(name="hard", passed=False), QACheck(name="ok", passed=True)])
    assert [c.name for c in r.hard_fails] == ["hard"]
    with pytest.raises(ValidationError):
        QAResult(job_id="j", artifact="email", passed=True)


@pytest.mark.parametrize("kw", [{"type": "bogus"}, {"needs": "desk"}, {"priority": "X"}])
def test_action_item_literals(kw):
    with pytest.raises(ValidationError):
        ActionItem(what="x", **kw)
    assert ActionItem(what="x").needs == "anytime"


def test_tracker_row_status_literal_and_posting_required_fields():
    with pytest.raises(ValidationError):
        TrackerRow(job_id="j", status="bogus")
    with pytest.raises(ValidationError):
        Posting(title="SWE", ats="lever")  # company missing


def test_tracker_row_from_posting_partial_salary_and_fallbacks():
    p = Posting(company="Acme", title="SWE", ats="lever", url="", apply_url="https://apply", salary_max=150000,
                fetched_at="2026-09-01T00:00:00+00:00")
    r = TrackerRow.from_posting(p, Score(job_id=p.job_id, category="swe_backend", fit=77, tier="C", prestige="a"), folder="/f")
    assert r.salary == "?-150,000"
    assert r.remote is None and r.location is None
    assert r.url == "https://apply" and r.date_found == "2026-09-01" and r.folder == "/f"
    assert (r.category, r.fit, r.tier, r.prestige) == ("swe_backend", 77, "C", "a")
    lo_only = TrackerRow.from_posting(Posting(company="A", title="t", ats="x", salary_min=90000, remote=False))
    assert lo_only.salary == "90,000-?" and lo_only.remote == "N"
