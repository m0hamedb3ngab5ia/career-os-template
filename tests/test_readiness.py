"""Unit tests for careeros.readiness: the checklist (REQ-102) and the apply gate (REQ-103)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from conftest import EXAMPLE_REPO, add_master_resume, personalize

from careeros import readiness

pytestmark = pytest.mark.unit


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
    assert set(open_musts(fresh(tmp_path))) == {"master_resume", "setup_clean"}


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
    assert str(e.value) == "not ready: master_resume" and e.value.items[0]["id"] == "master_resume"
