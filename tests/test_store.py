from __future__ import annotations

import json

import pytest

import careeros.store as store_mod
from careeros.models import Posting, QACheck, QAResult, Score
from careeros.store import Store, _is_finder_copy

pytestmark = pytest.mark.unit


def _post(jid="j1", **kw):
    return Posting(job_id=jid, company=kw.pop("company", "Acme"), title=kw.pop("title", "SWE"), ats="greenhouse", **kw)


def test_write_is_atomic_and_leaves_no_tmp(settings):
    st = Store(settings)
    st.save_posting(_post())
    files = sorted(p.name for p in st.job_dir("j1").iterdir())
    assert files == ["log.md", "posting.json", "status.json"]


def test_failed_write_keeps_previous_file(settings, monkeypatch):
    st = Store(settings)
    st.save_posting(_post(title="Original"))
    before = (st.job_dir("j1") / "posting.json").read_text()

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(store_mod.Path, "replace", boom)
    with pytest.raises(OSError):
        st.save_posting(_post(title="Changed"))
    monkeypatch.undo()
    assert (st.job_dir("j1") / "posting.json").read_text() == before
    assert st.load_posting("j1").title == "Original"


def test_status_found_only_on_first_save(settings):
    st = Store(settings)
    st.save_posting(_post())
    st.set_status("j1", "queued", "qa pass")
    st.save_posting(_post(title="SWE (updated)"))
    hist = json.loads((st.job_dir("j1") / "status.json").read_text())["history"]
    assert [h["status"] for h in hist] == ["found", "queued"]
    assert st.get_status("j1") == "queued"
    assert "status -> queued: qa pass" in st.read_log("j1")


def test_score_qa_answers_roundtrip(settings):
    st = Store(settings)
    st.save_posting(_post())
    st.save_score(Score(job_id="j1", category="swe_backend", fit=81, tier="B"))
    assert st.load_score("j1").fit == 81
    r = QAResult(job_id="j1", artifact="resume", passed=False, checks=[QACheck(name="x", passed=False)])
    st.save_qa("j1", r)
    assert st.load_qa("j1")[0].hard_fails[0].name == "x"
    st.save_answers("j1", {"q": "a"})
    assert st.load_answers("j1") == {"q": "a"}
    assert st.load_score("missing") is None and st.load_qa("missing") == [] and st.load_answers("missing") == {}
    assert st.get_status("missing") is None and st.read_log("missing") == ""


def test_seen_roundtrip_and_corrupt_file(settings):
    st = Store(settings)
    assert st.load_seen() == set()
    st.mark_seen(["b", "a"])
    assert json.loads(st.seen_file.read_text()) == ["a", "b"]
    st.seen_file.write_text("{corrupt")
    assert st.load_seen() == set()


def test_list_jobs_status_filter_and_score_fields(settings):
    st = Store(settings)
    st.save_posting(_post("j1"))
    st.save_posting(_post("j2", company="Initech"))
    st.set_status("j2", "queued")
    st.save_score(Score(job_id="j2", category="data_engineering", fit=90, tier="A"))
    (st.jobs_dir / "not_a_job").mkdir()  # dir without posting.json is ignored
    assert [j["job_id"] for j in st.list_jobs()] == ["j1", "j2"]
    (q,) = st.list_jobs("queued")
    assert q["company"] == "Initech" and q["fit"] == 90 and q["tier"] == "A"
    assert st.list_jobs("applied") == []
    assert st.list_jobs()[0]["fit"] is None


@pytest.mark.parametrize("name,dup", [
    ("posting 2.json", True), ("log 3.md", True), ("377debe1ff52 2", True), ("resume 12.tex", True),
    ("posting.json", False), ("377debe1ff52", False), ("cover_letter.md", False), ("resume_v2.pdf", False),
])
def test_finder_copy_names(name, dup):
    assert _is_finder_copy(name) is dup


def test_save_seen_uses_a_private_temp_file(settings, monkeypatch):
    """Two scouts writing seen.json must not share one temp path (one would replace the other's file)."""
    import os

    store = Store(settings)
    shared = store.seen_file.with_suffix(".tmp")
    shared.write_text("in use by another writer")
    store.save_seen({"a", "b"})
    assert shared.read_text() == "in use by another writer"
    assert store.load_seen() == {"a", "b"}
    assert not list(store.seen_file.parent.glob(f"*.{os.getpid()}.tmp"))


# --- posting history (ghost-job detection) -------------------------------------------------------------

def test_history_tracks_reposts_under_new_ids(settings):
    from careeros.models import Posting
    from careeros.store import Store

    st = Store(settings)
    a = Posting(company="Acme", title="Software Engineer", location="NY", ats="greenhouse", ats_job_id="1",
                posted_at="2026-08-01")
    b = Posting(company="Acme", title="Software Engineer", location="NY", ats="greenhouse", ats_job_id="2",
                posted_at="2026-09-20")
    hist = st.update_history([a], today="2026-08-02")
    hist = st.update_history([a, b], today="2026-09-21")
    e = st.load_history()[next(iter(hist))]
    assert e["ats_job_ids"] == ["1", "2"] and e["posted_at_min"] == "2026-08-01"
    assert e["first_seen"].startswith("2026-08-02") and e["last_seen"].startswith("2026-09-21")
    assert e["sightings"] == ["2026-08-01", "2026-09-20"]
    assert len(st.load_history()) == 1
