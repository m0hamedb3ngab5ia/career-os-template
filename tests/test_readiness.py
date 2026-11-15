"""Unit tests for careeros.readiness: the checklist (REQ-102) and the apply gate (REQ-103)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from conftest import EXAMPLE_REPO, add_master_resume, personalize

from careeros import readiness

pytestmark = [pytest.mark.unit, pytest.mark.readiness]


def which_all(name: str) -> str:
    return f"/fake/bin/{name}"


def fresh(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copytree(EXAMPLE_REPO / "config", root / "config")
    shutil.copytree(EXAMPLE_REPO / "profile", root / "profile")
    return root


def open_musts(root: Path, which=which_all) -> list[str]:
    return [i["id"] for i in readiness.items(root, which=which, env={}) if i["must"] and not i["done"]]


def test_items_have_the_contract_shape(tmp_path):
    its = readiness.items(fresh(tmp_path), which=which_all)
    assert {tuple(sorted(i)) for i in its} == {("done", "fix_link", "id", "label", "must")}
    assert {i["id"] for i in its if not i["must"]} == {"writing_sample", "credentials", "eeo_answers"}


def test_fresh_install_is_not_ready(tmp_path):
    assert set(open_musts(fresh(tmp_path))) == {"master_resume", "resume_look_approved", "setup_clean", "legal_answers", "salary_answer"}


def test_leftover_example_values_stay_open(tmp_path):
    root = personalize(fresh(tmp_path))
    assert open_musts(root) == []
    for rel in ("profile/standard_answers.yaml", "config/targets.yaml"):  # the example's INSERT lines, untouched
        shutil.copy(EXAMPLE_REPO / rel, root / rel)
    assert {"legal_answers", "salary_answer"} <= set(open_musts(root))


def test_reviewed_example_equal_answers_are_done(tmp_path):
    root = personalize(fresh(tmp_path))  # re-dumped: same "Yes"/"No"/90000 values, markers gone
    assert not {"legal_answers", "salary_answer"} & set(open_musts(root))


def test_paths_list_does_not_crash(tmp_path):
    root = personalize(fresh(tmp_path))
    (root / "config" / "pipeline.yaml").write_text("paths: [a, b]\n")
    assert "credentials" in {i["id"] for i in readiness.items(root, which=which_all, env={})}


def test_filled_root_is_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(readiness.shutil, "which", which_all)
    root = personalize(fresh(tmp_path))
    assert open_musts(root) == []
    readiness.require_ready(root)  # no raise


def test_each_must_have_opens(tmp_path):
    root = personalize(fresh(tmp_path))
    (root / "profile" / "master.proposed.yaml").write_text("{}")
    assert open_musts(root) == ["master_synced"]
    assert "claude" in open_musts(root, which=lambda n: None)
    shutil.rmtree(root / "profile" / "resumes")
    assert "master_resume" in open_musts(root)


def test_legal_and_salary_answers_must_be_set(tmp_path):
    import yaml
    root = personalize(fresh(tmp_path))
    p = root / "profile" / "standard_answers.yaml"
    d = yaml.safe_load(p.read_text())
    for a in d["answers"]:
        if a["key"] == "sponsorship":
            a["answer"] = None
    p.write_text(yaml.safe_dump(d))
    t = root / "config" / "targets.yaml"
    td = yaml.safe_load(t.read_text())
    td["candidate"]["salary_dropdown_floor_usd"] = None
    t.write_text(yaml.safe_dump(td))
    assert {"legal_answers", "salary_answer"} <= set(open_musts(root))


def test_require_ready_raises_listing_open_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(readiness.shutil, "which", which_all)
    root = add_master_resume(personalize(fresh(tmp_path)))
    shutil.rmtree(root / "profile" / "resumes")
    with pytest.raises(readiness.NotReady) as e:
        readiness.require_ready(root)
    assert str(e.value).startswith("not ready: Master résumé set") and e.value.items[0]["id"] == "master_resume"


def test_look_gate_needs_approval_and_resets_on_new_version(tmp_path):
    from careeros import master_sync

    root = personalize(fresh(tmp_path))
    assert "resume_look_approved" not in open_musts(root)
    (root / "profile" / "master.look.json").unlink()
    assert "resume_look_approved" in open_musts(root)
    master_sync.approve_look(root)
    assert open_musts(root) == []
    (root / "profile" / "master.look.json").write_text('{"rid": "master-0000", "version": 99}')
    assert "resume_look_approved" in open_musts(root)


def test_approve_look_without_master_raises(tmp_path):
    from careeros import master_sync

    with pytest.raises(LookupError):
        master_sync.approve_look(fresh(tmp_path))


def test_prepare_gate_checks_only_the_look(tmp_path, monkeypatch):
    """REQ-143: prepare spends tokens, so it waits for the look approval; other apply must-haves don't block it."""
    monkeypatch.setattr(readiness.shutil, "which", which_all)
    root = personalize(fresh(tmp_path))
    (root / "profile" / "master.look.json").unlink()
    with pytest.raises(readiness.NotReady) as e:
        readiness.require_ready(root, only=readiness.PREPARE_GATE)
    assert [i["id"] for i in e.value.items] == ["resume_look_approved"]
    from careeros import master_sync
    master_sync.approve_look(root)
    t = root / "config" / "targets.yaml"
    t.write_text(t.read_text().replace("salary_dropdown_floor_usd:", "old_floor:"))
    readiness.require_ready(root, only=readiness.PREPARE_GATE)  # salary still open: prepare not blocked
