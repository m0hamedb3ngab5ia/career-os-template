import pytest
from careeros.models import Posting
from careeros.scout import Prefilter, run_scout
from careeros.scout.base import BoardNotFound, FetchError
from careeros.store import Store

pytestmark = pytest.mark.unit


def _p(title, company="Acme", location="New York, NY", raw=None, ats="greenhouse", jid="1"):
    return Posting(company=company, title=title, location=location, ats=ats, ats_job_id=jid, raw=raw or {})


def test_prefilter_title_match(example_settings):
    pf = Prefilter(example_settings)
    assert pf.check(_p("Software Engineer, Backend"))[0]
    assert pf.check(_p("Senior Data Engineer"))[2] == "data_engineering"
    assert pf.check(_p("Full-Stack Engineer"))[2] == "swe_fullstack"
    assert pf.check(_p("SWE - New Grad"))[0]
    assert not pf.check(_p("Answer Desk Lead"))[0]  # 'swe' inside 'answer' must not match
    assert not pf.check(_p("Account Executive"))[0]
    assert pf.check(_p("Product Manager"))[1] == "title"
    assert pf.check(_p("Solutions Engineer"))[1] == "title"
    assert pf.check(_p("Hardware Engineer"))[1] == "title"


def test_prefilter_location_and_blocklist(example_settings):
    example_settings.targets["location"]["blocked_countries"] = ["DE"]
    pf = Prefilter(example_settings)
    assert pf.check(_p("Software Engineer", location="Berlin, Germany"))[1] == "location"
    assert pf.check(_p("Software Engineer", location="Remote", raw={"country": "DE"}))[1] == "location"
    assert pf.check(_p("Software Engineer", location="London, UK"))[0]
    assert pf.check(_p("Software Engineer", company="Globex Bank"))[1] == "blocklist"
    assert pf.check(_p("Software Engineer", company="DraftKings Inc."))[1] == "blocklist"
    assert pf.check(_p("Software Engineer", company="Acme"))[0]


def test_settings_helpers(example_settings):
    s = example_settings
    dream = s.merged_dream_list()
    assert dream[:3] == ["Stripe", "Databricks", "Anthropic"]  # explicit dream_list first, then auto tiers
    assert "Citadel" in dream and "Two Sigma" in dream and "Akuna Capital" in dream
    assert "Microsoft" not in dream and dream.count("Anthropic") == 1
    assert s.prestige_tier("Citadel Securities") == "sss"
    assert s.prestige_tier("citadel") == "sss"
    assert s.prestige_tier("Stripe, Inc.") == "a_plus"
    assert s.prestige_tier("Unknown Startup LLC") is None
    assert s.is_blocklisted("GLOBEX BANK PLC")
    assert not s.is_blocklisted("Stripe")
    assert s.is_dream("Two Sigma Investments")


def test_run_scout_with_fake_adapters(settings, monkeypatch):
    import careeros.scout as scout_mod

    class FakeGH:
        ats = "greenhouse"

        def fetch(self, board):
            return [
                _p("Software Engineer", company=board["company"], jid="a"),
                _p("Product Manager", company=board["company"], jid="b"),
                _p("Backend Engineer", company=board["company"], location="Munich, Germany", jid="c"),
            ]

    class FakeLever:
        ats = "lever"

        def fetch(self, board):
            raise BoardNotFound("nope")

    class FakeAshby:
        ats = "ashby"

        def fetch(self, board):
            raise FetchError("timeout")

    monkeypatch.setattr(scout_mod, "ADAPTERS", {"greenhouse": FakeGH, "lever": FakeLever, "ashby": FakeAshby})
    settings.targets["location"]["blocked_countries"] = ["DE"]
    settings.companies["boards"] = [
        {"company": "Acme", "ats": "greenhouse", "slug": "acme"},
        {"company": "Globex Bank", "ats": "greenhouse", "slug": "globex"},
        {"company": "Dead", "ats": "lever", "slug": "dead"},
        {"company": "Flaky", "ats": "ashby", "slug": "flaky"},
        {"company": "Custom Co", "ats": "custom", "url": "https://x"},
    ]
    store = Store(settings)
    logs: list[str] = []
    summary = run_scout(settings, store, log=logs.append)

    by = {b.company: b for b in summary.boards}
    assert by["Acme"].fetched == 3 and by["Acme"].stored == 1
    assert by["Acme"].filtered_title == 1 and by["Acme"].filtered_location == 1
    assert by["Globex Bank"].filtered_blocklist == 3 and by["Globex Bank"].stored == 0
    assert by["Dead"].status == "bad_slug"
    assert by["Flaky"].status == "error"
    assert by["Custom Co"].status == "skipped"
    assert any("custom scraper not implemented" in line for line in logs)
    assert [b.company for b in summary.bad_slugs] == ["Dead"]

    jobs = store.list_jobs()
    assert len(jobs) == 1 and jobs[0]["status"] == "found"
    assert len(store.load_seen()) == 6

    summary2 = run_scout(settings, store, log=logs.append)
    assert {b.company: b for b in summary2.boards}["Acme"].new == 0
    assert len(store.list_jobs()) == 1


def test_store_ignores_finder_duplicates(settings):
    import warnings

    from careeros.models import Posting

    store = Store(settings)
    store.save_posting(Posting(job_id="abc123", company="Acme", title="SWE", ats="greenhouse"))
    jd = store.job_dir("abc123")
    (jd / "posting 2.json").write_text("{not json")
    (jd / "log 2.md").write_text("stray")
    dup_dir = store.jobs_dir / "abc123 2"
    dup_dir.mkdir()
    (dup_dir / "posting.json").write_text((jd / "posting.json").read_text())
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        ids = list(store.iter_job_ids())
        jobs = store.list_jobs()
        store.list_jobs()  # second call: warning only once per Store
    assert ids == ["abc123"]
    assert [j["job_id"] for j in jobs] == ["abc123"]
    msgs = [str(x.message) for x in w if "Finder duplicate" in str(x.message)]
    assert len(msgs) == 1 and "abc123 2" in msgs[0]


def test_run_scout_refuses_without_title_keywords_and_marks_nothing_seen(settings, monkeypatch):
    import careeros.scout as scout_mod
    from careeros.config import ConfigError

    class FakeGH:
        ats = "greenhouse"

        def fetch(self, board):
            return [_p("Software Engineer", company=board["company"], jid="a")]

    monkeypatch.setattr(scout_mod, "ADAPTERS", {"greenhouse": FakeGH})
    settings.categories = {}  # missing/emptied categories.yaml: every title would be filtered and marked seen
    settings.companies["boards"] = [{"company": "Acme", "ats": "greenhouse", "slug": "acme"}]
    store = Store(settings)
    with pytest.raises(ConfigError, match="title_keywords"):
        run_scout(settings, store, log=lambda *_: None)
    assert store.load_seen() == set()
