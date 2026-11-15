"""`careeros job filters` end to end on a temp root: exit 3 + skip score.json on a hard fail, exit 0 + no file on a pass."""
from __future__ import annotations

import json
import subprocess

import pytest
from conftest import PY, personalize, subprocess_env

from careeros.config import get_settings
from careeros.models import Posting
from careeros.store import Store

pytestmark = pytest.mark.integration


def test_job_filters_cli(temp_root, tmp_path):
    root = personalize(temp_root)
    store = Store(get_settings(root))
    ids = {}
    for name, text in (("fail", "Requires 8+ years of experience."), ("pass", "2+ years of experience with Python.")):
        p = Posting(company="Nimbus", title="Software Engineer", ats="greenhouse", ats_job_id=name,
                    location="New York, NY", description_text=text, url=f"https://example.com/{name}")
        store.save_posting(p)
        ids[name] = p.job_id
    home = tmp_path / "home"
    home.mkdir()

    def cli(jid):
        return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), "job", "filters", jid],
                              capture_output=True, text=True, env=subprocess_env(root, home), timeout=120, cwd=root)

    r = cli(ids["fail"])
    assert r.returncode == 3, r.stderr
    sc = json.loads((store.job_dir(ids["fail"]) / "score.json").read_text())
    assert sc["decision"] == "skip" and sc["hard_filter_fails"] == ["yoe_gt_3"]
    r = cli(ids["pass"])
    assert r.returncode == 0, r.stderr
    assert not (store.job_dir(ids["pass"]) / "score.json").exists()
