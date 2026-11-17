"""Tracker: Reason column, Skipped sheet, closed-posting pruning, old-layout migration."""
from pathlib import Path

import pytest
from openpyxl import load_workbook

from careeros.models import TrackerRow
from careeros.tracker import JOB_COLUMNS, SKIPPED_COLUMNS, Tracker, posting_state, reason_for

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("note,want", [
    ("company_cap: score-job (run 20261014-191634-score-b631)", "Company application limit reached (90 days)"),
    ("yoe_gt_3 (run x)", "Asks for more than 3 years' experience"),
    ("prefilter: yoe_gt_5 (run x)", "Asks for more than 5 years' experience"),
    ("stale: posted >14 days, scored under pre-2026-11-15 rules", "Posting too old"),
    ("below_min_fit", "Fit score too low"),
    ("location_nonpreferred_low_fit", "Location not preferred and fit too low"),
    ("location_blocked", "Location not allowed"),
    ("sponsorship_required", "Needs visa sponsorship"),
    ("clearance_required", "Needs a security clearance"),
    ("company cooldown: 30 days", "Recent rejection at this company (cooldown)"),
    ("weird thing happened; more", "weird thing happened"),
    ("", ""),
])
def test_reason_for(note, want):
    assert reason_for(note) == want


def _sheet(path, name):
    ws = load_workbook(path)[name]
    return ws, {c.value: c.column for c in ws[1]}


def _ids(path, name):
    return [r[0].value for r in load_workbook(path)[name].iter_rows(min_row=2) if r[0].value]


def test_skipped_upsert_goes_to_skipped_sheet_only(tmp_path: Path):
    tr = Tracker(path=tmp_path / "t.xlsx")
    tr.upsert_job(TrackerRow(job_id="j1", company="Acme", role="SWE", status="found", url="https://x.example/1"))
    tr.upsert_job({"job_id": "j2", "company": "Beta", "role": "SRE", "status": "skipped", "fit": 40,
                   "url": "javascript:alert(1)", "notes": "yoe_gt_3 (run r)"})
    assert _ids(tr.path, "Jobs") == ["j1"]
    ws, h = _sheet(tr.path, "Skipped")
    row = [c.value for c in ws[2]]
    assert row[h["JobID"] - 1] == "j2" and row[h["Reason"] - 1] == "Asks for more than 3 years' experience"
    assert row[h["Posting"] - 1] == "open"
    assert ws.cell(row=2, column=h["URL"]).hyperlink is None
    assert [x[0] for x in SKIPPED_COLUMNS][:2] == ["JobID", "Company"]
    assert tr.get_job("j2")["Company"] == "Beta"


def test_job_moves_between_sheets_on_status_change(tmp_path: Path):
    tr = Tracker(path=tmp_path / "t.xlsx")
    tr.upsert_job({"job_id": "a", "company": "A", "role": "r", "status": "scored", "url": "https://a.example"})
    tr.upsert_job({"job_id": "b", "company": "B", "role": "r", "status": "scored"})
    tr.set_status("a", "skipped", "below_min_fit")
    assert _ids(tr.path, "Jobs") == ["b"] and _ids(tr.path, "Skipped") == ["a"]
    tr.set_status("a", "scored", "override")
    assert sorted(_ids(tr.path, "Jobs")) == ["a", "b"] and _ids(tr.path, "Skipped") == []
    assert tr.get_job("a")["Status"] == "scored" and "override" in tr.get_job("a")["Notes"]
    tr.upsert_job({"job_id": "a", "status": "skipped"})
    tr.upsert_job({"job_id": "a", "status": "queued"})
    assert _ids(tr.path, "Skipped") == []


def test_prune_closed_skipped_keeps_open(tmp_path: Path):
    tr = Tracker(path=tmp_path / "t.xlsx")
    tr.upsert_job({"job_id": "o", "status": "skipped", "posting": "open", "notes": "below_min_fit"})
    tr.upsert_job({"job_id": "c", "status": "skipped", "posting": "closed", "notes": "below_min_fit"})
    tr.upsert_job({"job_id": "n", "status": "skipped", "notes": "below_min_fit"})
    assert tr.prune_closed_skipped() == 1
    assert _ids(tr.path, "Skipped") == ["o", "n"]


def test_posting_state():
    t = "2026-11-15"
    assert posting_state("2026-11-01", None, None, 7, t) == "closed"
    assert posting_state(None, None, None, 7, t) == "open"  # no history: never drop on doubt
    assert posting_state(None, "2026-11-01T10:00:00", "2026-11-15T10:00:00", 7, t) == "closed"
    assert posting_state(None, "2026-11-10T10:00:00", "2026-11-15T10:00:00", 7, t) == "open"
    assert posting_state(None, "2026-11-01", "2026-11-15", 0, t) == "open"  # 0 = sightings rule off


def test_old_layout_workbook_is_rebuilt_keeping_cells(tmp_path: Path):
    from openpyxl.styles import Font

    tr = Tracker(path=tmp_path / "t.xlsx")
    tr.init()
    wb = load_workbook(tr.path)
    del wb["Skipped"]
    ws = wb["Jobs"]
    old = [h for h, _, _ in JOB_COLUMNS if h not in ("Reason", "Notes")]
    old.insert(old.index("Folder"), "Notes")  # the pre-Reason order
    old.append("MyCol")
    for i, h in enumerate(old, start=1):
        ws.cell(row=1, column=i, value=h)
    for r, (jid, st, note) in enumerate([("k1", "queued", "mine"), ("k2", "skipped", "company_cap: x")], start=2):
        vals = {"JobID": jid, "Company": "C", "Status": st, "Override": "A" if jid == "k1" else None,
                "NextAction": "call" if jid == "k1" else None, "Notes": note, "MyCol": "keep",
                "URL": "https://u.example/" + jid}
        for h, v in vals.items():
            ws.cell(row=r, column=old.index(h) + 1, value=v)
        c = ws.cell(row=r, column=old.index("URL") + 1)
        c.hyperlink = vals["URL"]
        c.font = Font(color="0563C1", underline="single")
    wb.save(tr.path)

    tr.set_config("touch", 1)  # any write persists the migration
    wb = load_workbook(tr.path)
    hdr = [c.value for c in wb["Jobs"][1]]
    assert hdr[: len(JOB_COLUMNS)] == [h for h, _, _ in JOB_COLUMNS] and hdr[-1] == "MyCol"
    assert hdr.index("Reason") == hdr.index("Status") + 1 and hdr.index("Notes") == hdr.index("Reason") + 1
    jobs = {j["JobID"]: j for j in tr.list_jobs()}
    assert list(jobs) == ["k1"]  # the skipped row moved to the Skipped sheet
    assert jobs["k1"]["Override"] == "A" and jobs["k1"]["NextAction"] == "call" and jobs["k1"]["MyCol"] == "keep"
    assert wb["Jobs"].cell(row=2, column=hdr.index("URL") + 1).hyperlink.target == "https://u.example/k1"
    sk = tr.get_job("k2")
    assert sk["Reason"] == "Company application limit reached (90 days)" and sk["Notes"] == "company_cap: x"


def test_move_between_sheets_keeps_override_and_custom_columns(tmp_path: Path):
    tr = Tracker(path=tmp_path / "t.xlsx")
    tr.upsert_job({"job_id": "m1", "company": "A", "role": "r", "status": "scored", "override": "A"})
    wb = load_workbook(tr.path)
    ws = wb["Jobs"]
    col = ws.max_column + 1
    ws.cell(row=1, column=col, value="MyCol")
    ws.cell(row=2, column=col, value="keep")
    wb.save(tr.path)

    tr.set_status("m1", "skipped", "below_min_fit")
    sk = tr.get_job("m1")
    assert sk["Override"] == "A" and sk["MyCol"] == "keep" and _ids(tr.path, "Jobs") == []
    tr.upsert_job({"job_id": "m1", "override": "B"})  # a skipped job's Override can be written
    assert tr.get_job("m1")["Override"] == "B"

    tr.set_status("m1", "scored")
    back = tr.list_jobs()[0]
    assert back["Override"] == "B" and back["MyCol"] == "keep" and _ids(tr.path, "Skipped") == []


def test_legacy_skipped_row_keeps_override_and_custom_columns(tmp_path: Path):
    tr = Tracker(path=tmp_path / "t.xlsx")
    tr.init()
    wb = load_workbook(tr.path)
    del wb["Skipped"]
    ws = wb["Jobs"]
    old = [h for h, _, _ in JOB_COLUMNS if h not in ("Reason", "Notes")] + ["Notes", "MyCol"]
    for i, h in enumerate(old, start=1):
        ws.cell(row=1, column=i, value=h)
    for h, v in {"JobID": "s1", "Company": "C", "Status": "skipped", "Override": "A", "MyCol": "keep"}.items():
        ws.cell(row=2, column=old.index(h) + 1, value=v)
    wb.save(tr.path)

    tr.set_config("touch", 1)
    sk = tr.get_job("s1")
    assert sk["Override"] == "A" and sk["MyCol"] == "keep" and _ids(tr.path, "Jobs") == []
