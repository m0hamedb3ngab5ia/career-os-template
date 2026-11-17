"""Network import + referral matching: the candidate's own LinkedIn Connections.csv export (never automated
LinkedIn access) matched against open jobs by normalized company name."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from careeros.network import (
    import_csv,
    load_network,
    match_jobs,
    network_path,
    parse_connections_csv,
    referral_action_text,
)

pytestmark = pytest.mark.unit

# LinkedIn's export starts with a notes block before the header row.
CSV = """Notes:
"When exporting your connection data, you may notice that some of the email addresses are missing."

First Name,Last Name,URL,Email Address,Company,Position,Connected On
Ada,Lovelace,https://www.linkedin.com/in/ada,,Quillstone Inc.,Staff Engineer,01 Mar 2024
Alan,Turing,https://www.linkedin.com/in/alan,alan@example.com,Acme Robotics,Recruiter,02 Apr 2023
Grace,Hopper,https://www.linkedin.com/in/grace,,,,03 May 2022
"""


def _write(tmp_path: Path, text: str = CSV) -> Path:
    f = tmp_path / "Connections.csv"
    f.write_text(text, encoding="utf-8")
    return f


def test_parse_skips_notes_header_and_blank_companies(tmp_path):
    rows = parse_connections_csv(_write(tmp_path))
    assert [r["name"] for r in rows] == ["Ada Lovelace", "Alan Turing"]
    assert rows[0] == {"name": "Ada Lovelace", "url": "https://www.linkedin.com/in/ada", "email": "",
                       "company": "Quillstone Inc.", "position": "Staff Engineer", "connected_on": "01 Mar 2024"}


def test_parse_without_notes_header(tmp_path):
    rows = parse_connections_csv(_write(tmp_path, CSV.split("\n", 3)[3]))
    assert len(rows) == 2


def test_parse_rejects_non_linkedin_csv(tmp_path):
    with pytest.raises(ValueError, match="First Name"):
        parse_connections_csv(_write(tmp_path, "a,b\n1,2\n"))


def test_import_writes_data_network_json(settings, tmp_path):
    n = import_csv(settings, _write(tmp_path))
    assert n == 2
    p = network_path(settings)
    assert p == settings.paths["jobs_dir"].parent / "network.json"
    data = json.loads(p.read_text())
    assert data["source"] == "Connections.csv" and len(data["connections"]) == 2
    assert load_network(settings) == data["connections"]


def test_load_network_missing_is_empty(settings):
    assert load_network(settings) == []


def _key(name: str) -> str:
    from careeros.config import normalize_company
    return {"acme": "acme robotics"}.get(normalize_company(name), normalize_company(name))


def test_match_by_normalized_company_and_alias():
    conns = [{"name": "Ada Lovelace", "company": "Quillstone Inc.", "position": "Staff Engineer", "url": "u1"},
             {"name": "Alan Turing", "company": "Acme Robotics", "position": "Recruiter", "url": "u2"}]
    jobs = [{"job_id": "j1", "company": "QuillStone", "title": "SWE", "status": "scored", "fit": 80},
            {"job_id": "j2", "company": "Acme", "title": "Backend", "status": "queued", "fit": 90},
            {"job_id": "j3", "company": "Nobody Co", "title": "X", "status": "scored", "fit": 99}]
    out = match_jobs(jobs, conns, _key)
    assert [m["job_id"] for m in out] == ["j2", "j1"]          # best fit first
    assert out[0]["connections"] == [{"name": "Alan Turing", "position": "Recruiter", "url": "u2"}]


def test_referral_action_text_names_everyone_capped():
    m = {"job_id": "j9", "company": "Acme", "title": "Backend", "connections": [
        {"name": f"P{i}", "position": "Eng", "url": ""} for i in range(5)]}
    t = referral_action_text(m)
    assert t.startswith("referral: ask P0 (Eng), P1 (Eng), P2 (Eng) +2 more at Acme for Backend")


def _root_with_job(tmp_path, company="Quillstone", status="scored"):
    from conftest import make_temp_root
    root = make_temp_root(tmp_path / "repo")
    d = root / "data" / "jobs" / "job000000001"
    d.mkdir(parents=True)
    (d / "posting.json").write_text(json.dumps({
        "job_id": "job000000001", "company": company, "title": "Software Engineer", "location": "NYC",
        "description_text": "x", "raw": {}, "ats": "greenhouse", "url": "https://x.test/1"}))
    (d / "status.json").write_text(json.dumps({"status": status}))
    return root


def test_cli_import_then_match_json(tmp_path, capsys):
    from careeros.cli import main
    root = _root_with_job(tmp_path)
    assert main(["--root", str(root), "network", "import", str(_write(tmp_path))]) == 0
    assert "2 connections" in capsys.readouterr().out
    assert main(["--root", str(root), "network", "match", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [(m["job_id"], m["connections"][0]["name"]) for m in out] == [("job000000001", "Ada Lovelace")]


def test_cli_match_status_filter_and_no_network(tmp_path, capsys):
    from careeros.cli import main
    root = _root_with_job(tmp_path, status="applied")
    assert main(["--root", str(root), "network", "match"]) == 1
    assert "network import" in capsys.readouterr().err
    main(["--root", str(root), "network", "import", str(_write(tmp_path))])
    capsys.readouterr()
    assert main(["--root", str(root), "network", "match", "--status", "scored", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_cli_match_actions_adds_one_deduped_item(tmp_path, capsys):
    from careeros.cli import main
    from careeros.config import Settings
    from careeros.tracker import Tracker
    root = _root_with_job(tmp_path)
    main(["--root", str(root), "network", "import", str(_write(tmp_path))])
    for _ in range(2):
        assert main(["--root", str(root), "network", "match", "--job", "job000000001", "--actions"]) == 0
    items = Tracker(settings=Settings.load(root)).list_action_items(open_only=True)
    assert [i["What to do"] for i in items if i["JobID"] == "job000000001"] == [
        "referral: ask Ada Lovelace (Staff Engineer) at Quillstone for Software Engineer; "
        "draft with /draft-outreach job000000001"]


def test_cli_referral_item_does_not_swallow_draft_outreach_item(tmp_path, capsys):
    """draft-outreach opens its own send_linkedin item with `--dedupe` (job + type); the referral item must not
    block it, and a second referral run must not add a duplicate."""
    from careeros.cli import main
    from careeros.config import Settings
    from careeros.tracker import Tracker, add_action
    root = _root_with_job(tmp_path)
    main(["--root", str(root), "network", "import", str(_write(tmp_path))])
    main(["--root", str(root), "network", "match", "--job", "job000000001", "--actions"])
    s = Settings.load(root)
    msg = add_action(s, "tailor by hand: Ada Lovelace", "send_linkedin", job_id="job000000001", dedupe=True)
    assert "added" in msg
    main(["--root", str(root), "network", "match", "--job", "job000000001", "--actions"])
    whats = [i["What to do"] for i in Tracker(settings=s).list_action_items(open_only=True)]
    assert sum(w.startswith("referral:") for w in whats) == 1 and "tailor by hand: Ada Lovelace" in whats
