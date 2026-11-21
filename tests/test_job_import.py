"""`careeros job add <url>` and `--from-alert` (REQ-153): one posting from a URL or a job-alert email."""
from __future__ import annotations

import json

import pytest

from careeros import job_import as ji
from careeros.models import Posting
from careeros.store import Store

pytestmark = pytest.mark.unit


UUID = "12345678-1234-1234-1234-123456789abc"


def test_parse_embed_eu_and_custom_domain_links():
    assert ji.parse_url("https://job-boards.greenhouse.io/embed/job_app?for=acme&token=123") == ("greenhouse", "acme", "123")
    assert ji.parse_url("https://job-boards.eu.greenhouse.io/acme/jobs/55") == ("greenhouse", "acme", "55")
    assert ji.parse_url(f"https://jobs.eu.lever.co/acme/{UUID}") == ("lever", "acme", UUID)
    assert ji.parse_url("https://acme.com/careers?gh_jid=777")[::2] == ("greenhouse", "777")


def test_describe_makes_alert_job_score_eligible(settings):
    from datetime import datetime, timezone

    from careeros.runs.runner import load_runs_config, select_candidates

    now = datetime.now(timezone.utc)
    r = ji.add_alerts(settings, [{"title": "Software Engineer", "company": "Acme", "url": "https://www.linkedin.com/jobs/view/42"}])[0]
    _, ex = select_candidates(settings, "score", load_runs_config(settings), now, job_ids=[r["job_id"]])
    assert any(e["reason"] == "needs description" for e in ex)
    ji.describe(settings, r["job_id"], "Build backend services in Python.")
    p = Store(settings).load_posting(r["job_id"])
    assert p.description_text.startswith("Build backend") and not p.raw.get("needs_description")
    sel, ex = select_candidates(settings, "score", load_runs_config(settings), now, job_ids=[r["job_id"]])
    assert not any(e["reason"] == "needs description" for e in ex)


def test_describe_unknown_job_and_empty_text(settings):
    with pytest.raises(ji.ImportError_, match="not found"):
        ji.describe(settings, "nope", "x")
    r = ji.add_alerts(settings, [{"title": "T", "company": "C", "url": "https://www.indeed.com/viewjob?jk=a"}])[0]
    with pytest.raises(ji.ImportError_, match="empty"):
        ji.describe(settings, r["job_id"], "  ")


@pytest.fixture
def cli(settings, monkeypatch):
    import careeros.cli as cli_mod

    monkeypatch.setattr(cli_mod, "_settings", lambda args: settings)
    return cli_mod.main


def test_parse_ats_urls():
    assert ji.parse_url("https://boards.greenhouse.io/acme/jobs/123?gh_src=x") == ("greenhouse", "acme", "123")
    assert ji.parse_url("https://job-boards.greenhouse.io/acme/jobs/123") == ("greenhouse", "acme", "123")
    assert ji.parse_url(f"https://jobs.lever.co/acme/{UUID}/apply") == ("lever", "acme", UUID)
    assert ji.parse_url(f"https://jobs.ashbyhq.com/acme/{UUID}") == ("ashby", "acme", UUID)
    assert ji.parse_url("https://acme.joinhandshake.com/jobs/9")[0] == "handshake"
    assert ji.parse_url("https://careers.example.com/role")[0] == "manual"


def test_add_ats_job_stores_posting_and_dedups(settings, monkeypatch):
    def fake_fetch(self, board):
        return [Posting(company=board["company"], title="Other", ats="greenhouse", ats_job_id="1"),
                Posting(company=board["company"], title="Backend Engineer", ats="greenhouse", ats_job_id="123",
                        url="https://boards.greenhouse.io/acme/jobs/123", description_text="Build things")]
    monkeypatch.setattr("careeros.scout.greenhouse.GreenhouseAdapter.fetch", fake_fetch)
    url = "https://boards.greenhouse.io/acme/jobs/123"
    r1 = ji.add_url(settings, url)
    assert r1["status"] == "added" and r1["title"] == "Backend Engineer"
    st = Store(settings)
    assert st.exists(r1["job_id"]) and st.get_status(r1["job_id"]) == "found"
    r2 = ji.add_url(settings, url)
    assert r2["status"] == "exists" and r2["job_id"] == r1["job_id"]


def test_add_ats_job_not_on_board(settings, monkeypatch):
    monkeypatch.setattr("careeros.scout.greenhouse.GreenhouseAdapter.fetch", lambda self, b: [])
    with pytest.raises(ji.ImportError_, match="not found"):
        ji.add_url(settings, "https://boards.greenhouse.io/acme/jobs/999")


def test_manual_page_becomes_ats_manual(settings, monkeypatch):
    html = ("<html><head><title>Data Engineer | Initech</title><meta property='og:site_name' content='Initech'>"
            "</head><body><h1>Data Engineer</h1><p>Own the pipelines.</p></body></html>")
    monkeypatch.setattr(ji, "_get_html", lambda url: html)
    r = ji.add_url(settings, "https://careers.initech.com/de")
    assert r["status"] == "added"
    p = Store(settings).load_posting(r["job_id"])
    assert p.ats == "manual" and p.company == "Initech" and "Own the pipelines" in p.description_text
    assert ji.add_url(settings, "https://careers.initech.com/de")["status"] == "exists"


def test_handshake_needs_browser(settings):
    with pytest.raises(ji.ImportError_, match="signed-in browser"):
        ji.add_url(settings, "https://app.joinhandshake.com/jobs/9")


def test_alert_items_import_without_fetching(settings, monkeypatch):
    monkeypatch.setattr(ji, "_get_html", lambda url: pytest.fail("alert import must not fetch"))
    items = [{"title": "SWE", "company": "Acme", "url": "https://www.linkedin.com/jobs/view/4000111222/?trk=x"},
             {"title": "SWE", "company": "Acme", "url": "https://www.linkedin.com/comm/jobs/view/4000111222"},
             {"title": "Backend Dev", "company": "Globex", "url": "https://www.indeed.com/viewjob?jk=abc123&from=alert"},
             {"title": "", "company": "X", "url": ""}]
    out = ji.add_alerts(settings, items)
    assert [o["status"] for o in out] == ["added", "exists", "added", "skipped"]
    p = Store(settings).load_posting(out[0]["job_id"])
    assert p.ats == "linkedin" and p.raw["source"] == "job_alert" and p.description_text == ""
    assert Store(settings).load_posting(out[2]["job_id"]).ats == "indeed"


def test_cli_add(cli, settings, monkeypatch, capsys, tmp_path):
    f = tmp_path / "alert.json"
    f.write_text(json.dumps([{"title": "SWE", "company": "Acme", "url": "https://www.linkedin.com/jobs/view/1"}]))
    assert cli(["job", "add", "--from-alert", str(f)]) == 0
    assert "added" in capsys.readouterr().out
    assert cli(["job", "add", "https://app.joinhandshake.com/jobs/9"]) == 1
    assert "signed-in browser" in capsys.readouterr().err


def test_handshake_alert_maps_to_scout_job_url(settings):
    from careeros.scout.handshake import JOB_URL

    r = ji.add_alerts(settings, [{"title": "Software Engineer", "company": "Acme",
                                  "url": "https://app.joinhandshake.com/stu/jobs/9876543?ref=email"}])[0]
    p = Store(settings).load_posting(r["job_id"])
    assert (p.ats, p.ats_job_id, p.url) == ("handshake", "9876543", JOB_URL.format(id="9876543"))
