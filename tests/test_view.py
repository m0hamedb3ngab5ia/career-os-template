"""`careeros view`: the three sections render from disk and all text is escaped."""
from __future__ import annotations

import shutil

import pytest
from conftest import EXAMPLE_REPO, personalize

from careeros import view
from careeros.config import get_settings
from careeros.models import Posting
from careeros.store import Store

pytestmark = [pytest.mark.unit, pytest.mark.readiness]


def test_view_sections_and_escaping(temp_root):
    store = Store(get_settings(temp_root))
    p = Posting(job_id="j1", company="<script>alert(1)</script> & Co", title="Eng", location="x", ats="greenhouse",
                url="https://e.test/1", description="d", fetched_at="2026-01-01T00:00:00Z")
    store.save_posting(p)
    store.set_status("j1", "applied")
    store.save_posting(Posting(job_id="j2", company="Later Inc", title="Eng", location="x", ats="greenhouse",
                               url="https://e.test/2", description="d", fetched_at="2026-01-01T00:00:00Z"))
    store.set_status("j2", "applied")
    store.set_status("j2", "interview")  # moved past applied: still an application
    out = view.write(temp_root)
    d = temp_root / "data" / "views"
    assert out == d / "setup.html"  # setup not finished: open Setup first
    setup, jobs, apps = ((d / f"{n}.html").read_text(encoding="utf-8") for n in ("setup", "jobs", "applications"))
    for page in (setup, jobs, apps):
        assert all(f'href="{n}.html"' in page for n in ("setup", "jobs", "applications")) and "<script" not in page
    assert "Getting set up" in setup and " done</p>" in setup and "<progress" in setup
    assert "Add your résumé" in setup and "todo:" not in setup and "done:" not in setup  # checkmarks, not prefixes
    assert "careeros" not in setup.split("<body>")[1]  # plain words, no commands
    assert "Applications" not in setup.split("</nav>")[1] and "Applied</td>" in jobs
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; Co" in apps
    assert "<td>Later Inc</td>" in apps and "Interviewing</td>" in apps


def test_view_documents_tab_replaces_setup_once_ready(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    for d in ("config", "profile"):
        shutil.copytree(EXAMPLE_REPO / d, root / d)
    root = personalize(root)
    real = view.readiness.items
    monkeypatch.setattr(view.readiness, "items", lambda r: [{**i, "done": True} for i in real(r)])  # no `claude` in CI
    (root / "data" / "views").mkdir(parents=True)
    (root / "data" / "views" / "setup.html").write_text("old")
    out = view.write(root)
    d = root / "data" / "views"
    assert out == d / "documents.html" and not (d / "setup.html").exists()
    docs = out.read_text(encoding="utf-8")
    assert "<h1>Documents</h1>" in docs and "<td>Master</td>" in docs and "Every job" in docs
    assert "Needs your OK" not in docs  # personalize() approved the look
    assert 'href="setup.html"' not in (d / "jobs.html").read_text(encoding="utf-8")


def test_view_search_tab_lists_filters_and_funnel(temp_root):
    import json

    s = get_settings(temp_root)
    s.paths["seen_file"].parent.mkdir(parents=True, exist_ok=True)
    (s.paths["seen_file"].parent / "scout_last.json").write_text(json.dumps(
        {"at": "2026-11-14T10:00:00+00:00", "fetched": 1500, "new": 1200, "stored": 35,
         "filtered": {"location": 400, "seniority": 300, "title": 465}}))
    view.write(temp_root)
    d = temp_root / "data" / "views"
    page = (d / "search.html").read_text(encoding="utf-8")
    assert 'href="search.html"' in (d / "jobs.html").read_text(encoding="utf-8") and "<script" not in page and "<form" not in page
    for what in ("Posted within", "Work mode", "Minimum salary", "Blocked companies", "Senior titles skipped",
                 "Also OK job types", "Job types skipped", "Preferred countries", "Allowed countries",
                 "Lowest fit outside preferred places", "Industries never applied to", "Company names skipped",
                 "Job boards searched", "Search filters turned off"):
        assert what in page
    assert "Only jobs posted in the last 14 days" in page and "Any age" in page  # value now + sentence to say
    assert "1,200" in page and "35" in page and "Nov 14, 2026" in page and "Blocked countries" in page
    assert "careeros" not in page.split("<body>")[1]  # plain words, no commands
    (s.paths["seen_file"].parent / "scout_last.json").unlink()
    view.write(temp_root)
    assert "No search yet" in (d / "search.html").read_text(encoding="utf-8")
