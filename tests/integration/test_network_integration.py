"""`careeros network import|match` as a subprocess on a temp root: data/network.json, JSON stdout with --actions,
one deduped `referral` Action Item in the tracker."""
from __future__ import annotations

import json
import subprocess

import pytest
from conftest import PY, subprocess_env

from careeros.config import Settings
from careeros.models import Posting
from careeros.store import Store
from careeros.tracker import Tracker

pytestmark = pytest.mark.integration

CSV = ("Notes:\n\"export notes\"\n\nFirst Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
       "Ada,Lovelace,https://www.linkedin.com/in/ada,,Nimbus Inc.,Staff Engineer,01 Mar 2024\n")


def test_network_cli_end_to_end(temp_root, tmp_path):
    store = Store(Settings.load(temp_root))
    p = Posting(company="Nimbus", title="Software Engineer", ats="greenhouse", ats_job_id="1",
                location="Austin, TX", description_text="x", url="https://example.com/1")
    store.save_posting(p)
    store.set_status(p.job_id, "scored")
    csv = tmp_path / "Connections.csv"
    csv.write_text(CSV, encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()

    def cli(*a):
        return subprocess.run([PY, "-m", "careeros.cli", "--root", str(temp_root), "network", *a],
                              capture_output=True, text=True, env=subprocess_env(temp_root, home), timeout=120)

    r = cli("import", str(csv))
    assert r.returncode == 0, r.stderr
    assert json.loads((temp_root / "data" / "network.json").read_text())["connections"][0]["name"] == "Ada Lovelace"
    for _ in range(2):
        r = cli("match", "--actions", "--json")
        assert r.returncode == 0, r.stderr
        assert [m["job_id"] for m in json.loads(r.stdout)] == [p.job_id]   # stdout stays valid JSON
    items = Tracker(settings=Settings.load(temp_root)).list_action_items(open_only=True)
    assert [i["Type"] for i in items if i["JobID"] == p.job_id] == ["referral"]
