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
    example_settings.companies["blocklist"] = {"companies": ["Globex Bank"], "name_patterns": ["draftkings"]}
    pf = Prefilter(example_settings)
    assert pf.check(_p("Software Engineer", location="Berlin, Germany"))[1] == "location"
    assert pf.check(_p("Software Engineer", location="Remote", raw={"country": "DE"}))[1] == "location"
    assert pf.check(_p("Software Engineer", location="London, UK"))[0]
    assert pf.check(_p("Software Engineer", company="Globex Bank"))[1] == "blocklist"
    assert pf.check(_p("Software Engineer", company="DraftKings Inc."))[1] == "blocklist"
    assert pf.check(_p("Software Engineer", company="Acme"))[0]


def test_settings_helpers(example_settings):
    s = example_settings
    s.companies["dream_list"] = ["Stripe", "Databricks", "Anthropic"]
    s.companies["blocklist"] = {"companies": ["Globex Bank"]}
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


def test_scout_sources_and_filters_are_configurable(settings, monkeypatch):
    """targets.yaml `scout.sources` limits which ATS families are fetched; `scout.filters` turns single
    prefilter steps off (a template user who wants senior roles sets seniority: false)."""
    import careeros.scout as scout_mod

    class Fake:
        def fetch(self, board):
            return [_p("Senior Software Engineer", company=board["company"], jid=board["slug"])]

    monkeypatch.setattr(scout_mod, "ADAPTERS", {"greenhouse": Fake, "lever": Fake})
    settings.companies["boards"] = [{"company": "Acme", "ats": "greenhouse", "slug": "a"},
                                    {"company": "Beta", "ats": "lever", "slug": "b"}]
    settings.targets["scout"] = {"sources": ["greenhouse"], "filters": {"seniority": False}}
    summary = run_scout(settings, Store(settings), log=lambda *_: None)
    status = {b.company: b.status for b in summary.boards}
    assert status == {"Acme": "ok", "Beta": "skipped"}
    assert summary.totals["stored"] == 1 and summary.totals["filtered_seniority"] == 0


def test_scout_defaults_keep_every_filter_on(example_settings):
    from careeros.scout import scout_config

    cfg = scout_config(example_settings)
    assert cfg["sources"] == ["greenhouse", "lever", "ashby", "handshake", "simplify"]
    assert all(cfg["filters"].values()) and set(cfg["filters"]) == {
        "blocklist", "flagged", "title", "seniority", "location", "ghost"}


def _dated(days_ago, **kw):
    from datetime import date, timedelta
    p = _p("Software Engineer", **kw)
    p.posted_at = (date.today() - timedelta(days=days_ago)).isoformat()
    return p


def test_prefilter_max_post_age_days(example_settings):
    assert Prefilter(example_settings).check(_dated(400))[0]  # default null = off
    example_settings.targets.setdefault("scout", {})["max_post_age_days"] = 14
    pf = Prefilter(example_settings)
    assert pf.check(_dated(5))[0]
    assert pf.check(_dated(30))[1:2] == ("age",)
    assert pf.check(_p("Software Engineer"))[0]  # no date: kept


def test_prefilter_new_grad_max_post_age_days(example_settings):
    sc = example_settings.targets.setdefault("scout", {})
    sc["max_post_age_days"], sc["new_grad_max_post_age_days"] = 14, 60

    def grad(title, days):
        p = _dated(days)
        p.title = title
        return p

    pf = Prefilter(example_settings)
    for t in ("Software Engineer, New Grad", "Graduate Software Engineer (2027 Start)", "Entry-Level Software Engineer",
              "Software Engineer - University Graduate", "Early Career Software Engineer", "New College Grad SWE"):
        assert pf.check(grad(t, 45))[0], t  # new-grad titles get the longer window
        assert pf.check(grad(t, 70))[1:2] == ("age",), t
    assert pf.check(grad("Software Engineer", 45))[1:2] == ("age",)  # everything else keeps 14 days
    sc["max_post_age_days"] = None  # general window off: the new-grad window still applies to new-grad titles
    assert Prefilter(example_settings).check(grad("Software Engineer, New Grad", 70))[1:2] == ("age",)
    assert Prefilter(example_settings).check(grad("Software Engineer", 400))[0]
    sc["max_post_age_days"] = 14
    sc.pop("new_grad_max_post_age_days")
    assert Prefilter(example_settings).check(grad("Software Engineer, New Grad", 45))[1:2] == ("age",)  # unset = same


def test_prefilter_work_modes(example_settings):
    example_settings.targets["location"]["work_modes"] = ["remote", "hybrid"]
    pf = Prefilter(example_settings)
    assert pf.check(_p("Software Engineer", raw={"workplaceType": "OnSite"}))[1] == "work_mode"
    assert pf.check(_p("Software Engineer", location="Austin, TX (On-site)"))[1] == "work_mode"
    assert pf.check(_p("Software Engineer", raw={"workplaceType": "Hybrid"}))[0]
    assert pf.check(_p("Software Engineer", location="Remote - US"))[0]
    assert pf.check(_p("Software Engineer"))[0]  # mode unknown: kept
    example_settings.targets["location"]["work_modes"] = ["onsite"]
    assert Prefilter(example_settings).check(_p("Software Engineer", location="Remote - US"))[1] == "work_mode"
    example_settings.targets["location"]["work_modes"] = ["remote", "hybrid", "onsite"]
    assert Prefilter(example_settings).check(_p("Software Engineer", raw={"workplaceType": "OnSite"}))[0]


def test_run_scout_saves_funnel(settings, monkeypatch):
    import json

    import careeros.scout as scout_mod

    class Fake:
        def fetch(self, board):
            return [_p("Software Engineer", jid="a"), _p("Senior Software Engineer", jid="b"),
                    _p("Software Engineer", jid="c", raw={"workplaceType": "onsite"})]

    monkeypatch.setattr(scout_mod, "ADAPTERS", {"greenhouse": Fake})
    settings.companies["boards"] = [{"company": "Acme", "ats": "greenhouse", "slug": "a"}]
    settings.targets["location"]["work_modes"] = ["remote", "hybrid"]
    run_scout(settings, Store(settings), log=lambda *_: None)
    doc = json.loads((settings.paths["seen_file"].parent / "scout_last.json").read_text())
    assert doc["new"] == 3 and doc["stored"] == 1 and doc["at"]
    assert doc["filtered"]["seniority"] == 1 and doc["filtered"]["work_mode"] == 1 and doc["filtered"]["location"] == 0
