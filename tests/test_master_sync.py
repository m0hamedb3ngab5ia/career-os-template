"""master.yaml diff from the master résumé (REQ-099, UC-003, TASK-009): propose -> pending; approve writes, reject
keeps master.yaml untouched; readiness `master_synced` stays open while a proposal is pending or rejected (REQ-102)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from conftest import EXAMPLE_REPO

from careeros import master_sync, readiness

pytestmark = [pytest.mark.unit, pytest.mark.readiness]


def _root(tmp_path: Path, resume_text: str) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(EXAMPLE_REPO / "profile", root / "profile")
    d = root / "profile" / "resumes" / "master-0000"
    (d / "v1").mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"rid": "master-0000", "name": "M", "type": "master", "versions": [
        {"n": 1, "author": "user", "source": "upload", "at": "2026-10-04T00:00:00Z"}]}), encoding="utf-8")
    (d / "v1" / "ats.json").write_text(json.dumps({"text": resume_text, "warnings": []}), encoding="utf-8")
    return root


def _proposal(root: Path, text: str) -> str:
    """Current master.yaml with the first experience bullet's text replaced."""
    d = yaml.safe_load((root / "profile" / "master.yaml").read_text(encoding="utf-8"))
    d["experience"][0]["bullets"][0]["text"] = text
    return yaml.safe_dump(d, sort_keys=False, allow_unicode=True)


def _synced(root: Path) -> bool:
    return next(i for i in readiness.items(root, which=lambda n: "/x", env={}) if i["id"] == "master_synced")["done"]


def test_propose_then_approve_writes_exactly_the_proposal(tmp_path):
    root = _root(tmp_path, "Cut p99 latency by 37% across 12 services")
    before = (root / "profile" / "master.yaml").read_text(encoding="utf-8")
    assert master_sync.state(root)["state"] == "stale" and not _synced(root)  # never synced from this master
    text = _proposal(root, "Cut p99 latency by 37% across 12 services")
    master_sync.propose(root, text)
    st = master_sync.state(root)
    assert st["state"] == "pending" and "+" in st["diff"] and "37%" in st["diff"]
    assert (root / "profile" / "master.yaml").read_text(encoding="utf-8") == before  # untouched until approve
    assert not _synced(root)
    master_sync.approve(root)
    assert (root / "profile" / "master.yaml").read_text(encoding="utf-8") == text
    assert master_sync.state(root) == {"state": "synced", "diff": ""} and _synced(root)


def test_reject_keeps_master_and_readiness_open(tmp_path):
    root = _root(tmp_path, "Shipped 3 releases")
    before = (root / "profile" / "master.yaml").read_text(encoding="utf-8")
    master_sync.propose(root, _proposal(root, "Shipped 3 releases"))
    master_sync.reject(root)
    assert (root / "profile" / "master.yaml").read_text(encoding="utf-8") == before
    assert master_sync.state(root)["state"] == "rejected" and not _synced(root)
    with pytest.raises(LookupError):
        master_sync.approve(root)  # nothing pending: a rejected proposal can't be approved
    master_sync.propose(root, _proposal(root, "Shipped 3 releases"))  # a fresh proposal replaces the rejection
    master_sync.approve(root)
    assert _synced(root)


def test_invented_number_refused(tmp_path):
    root = _root(tmp_path, "Cut latency by 37%")
    with pytest.raises(master_sync.Invalid, match="4173"):
        master_sync.propose(root, _proposal(root, "Cut latency by 4173%"))
    assert master_sync.state(root)["state"] == "stale"  # nothing stored


def test_schema_checked_like_master_yaml(tmp_path):
    root = _root(tmp_path, "")
    with pytest.raises(master_sync.Invalid, match="identity"):
        master_sync.propose(root, "experience: []\n")
    with pytest.raises(master_sync.Invalid):
        master_sync.propose(root, "- not a mapping\n")


def test_tampered_proposal_not_approved(tmp_path):
    root = _root(tmp_path, "Shipped 3 releases")
    before = (root / "profile" / "master.yaml").read_text(encoding="utf-8")
    master_sync.propose(root, _proposal(root, "Shipped 3 releases"))
    (root / "profile" / "master.proposed.yaml").write_text(_proposal(root, "Shipped 9917 releases"), encoding="utf-8")
    with pytest.raises(master_sync.Invalid, match="9917"):
        master_sync.approve(root)
    assert (root / "profile" / "master.yaml").read_text(encoding="utf-8") == before


def test_no_master_resume_refused(tmp_path):
    root = _root(tmp_path, "")
    shutil.rmtree(root / "profile" / "resumes")
    with pytest.raises(master_sync.Invalid, match="master résumé"):
        master_sync.propose(root, (root / "profile" / "master.yaml").read_text(encoding="utf-8"))


def test_number_guard_is_exact_tokens_and_covers_variants(tmp_path):
    """Review #126: "20" must not pass because "2020" is in the source; variants/summary_variants are checked too."""
    root = _root(tmp_path, "Engineer 2019-2020")
    (root / "profile" / "master.yaml").write_text("", encoding="utf-8")  # source = the résumé only
    base = yaml.safe_load((EXAMPLE_REPO / "profile" / "master.yaml").read_text(encoding="utf-8"))

    def strip(d):  # no numbers anywhere except what a test plants
        import re
        return yaml.safe_load(re.sub(r"\d", "x", yaml.safe_dump(d, allow_unicode=True)))

    for plant, bad in ((lambda d: d["experience"][0]["bullets"][0].update(text="Cut latency 20% across 9 services"), "20"),
                       (lambda d: d["experience"][0]["bullets"][0].update(variants={"short": "Served 999 users"}), "999"),
                       (lambda d: d.update(summary_variants={"general": "Led 77 engineers"}), "77")):
        d = strip(base)
        plant(d)
        with pytest.raises(master_sync.Invalid, match=bad):
            master_sync.propose(root, yaml.safe_dump(d, sort_keys=False, allow_unicode=True))


def test_malformed_identity_is_a_validation_problem(tmp_path):
    root = _root(tmp_path, "x")
    with pytest.raises(master_sync.Invalid):
        master_sync.propose(root, "identity: x\n")


def test_new_master_resume_makes_master_yaml_stale(tmp_path):
    """Review #126 MUST 1: approve records the source résumé; another master (or version) -> stale, readiness open."""
    root = _root(tmp_path, "Shipped 3 releases")
    master_sync.propose(root, _proposal(root, "Shipped 3 releases"))
    master_sync.approve(root)
    assert master_sync.state(root)["state"] == "synced" and _synced(root)
    meta = root / "profile" / "resumes" / "master-0000" / "meta.json"
    m = json.loads(meta.read_text(encoding="utf-8"))
    m["versions"].append({"n": 2, "author": "user", "source": "upload", "at": "2026-10-05T00:00:00Z"})
    meta.write_text(json.dumps(m), encoding="utf-8")
    assert master_sync.state(root)["state"] == "stale" and not _synced(root)
