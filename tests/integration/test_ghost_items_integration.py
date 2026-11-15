"""`careeros safety ghost-items` end to end on a temp root: CLI dispatch, tracker writes, rerun, --close-stale."""
from __future__ import annotations

import subprocess

import pytest
import yaml
from conftest import PY, personalize, subprocess_env

from careeros.config import get_settings
from careeros.models import Posting, Score
from careeros.store import Store
from careeros.tracker import Tracker

pytestmark = pytest.mark.integration


def test_ghost_items_cli(temp_root, tmp_path):
    root = personalize(temp_root)
    cfg = root / "config" / "companies.yaml"
    data = yaml.safe_load(cfg.read_text()) or {}
    data["dream_list"] = ["Nimbus"]
    cfg.write_text(yaml.safe_dump(data))
    s = get_settings(root)
    store, tr = Store(s), Tracker(settings=s)
    tr.init()
    for n in range(2):
        p = Posting(company="Nimbus", title=f"Engineer {n}", ats="greenhouse", ats_job_id=str(n), posted_at="2024-01-01",
                    last_updated="2024-01-01", description_text="We are hiring.", url=f"https://example.com/{n}")
        store.save_posting(p)
        store.save_score(Score(job_id=p.job_id, category="swe_backend", fit=85))
    tr.add_action_item("possible ghost job", "ghost_job", job_id="gone", company="Nimbus")
    home = tmp_path / "home"
    home.mkdir()

    def cli(*a):
        r = subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), "safety", "ghost-items", *a],
                           capture_output=True, text=True, env=subprocess_env(root, home), timeout=120, cwd=root)
        assert r.returncode == 0, r.stderr
        return r.stdout

    assert "would close 1" in cli("--close-stale", "--dry-run")
    assert len([i for i in tr.list_action_items() if i["Type"] == "ghost_job"]) == 1  # dry run wrote nothing
    cli("--close-stale")
    cli()                                                                             # rerun: no duplicate
    items = [i for i in tr.list_action_items() if i["Type"] == "ghost_job"]
    assert len(items) == 1 and "2 jobs" in items[0]["What to do"]
