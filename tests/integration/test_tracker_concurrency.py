"""Two processes writing the same JobTracker.xlsx at once must not lose each other's rows."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from conftest import PY, ROOT
from careeros.tracker import Tracker

pytestmark = pytest.mark.integration

WRITER = """
import sys
from careeros.tracker import Tracker
t = Tracker(path=sys.argv[1])
for i in range(int(sys.argv[3])):
    t.upsert_job({"job_id": f"{sys.argv[2]}{i}", "company": "Acme"})
    t.add_action_item(f"{sys.argv[2]}{i}", id=f"{sys.argv[2]}a{i}")
"""


def test_concurrent_writers_keep_every_row(tmp_path: Path):
    path = tmp_path / "JobTracker.xlsx"
    Tracker(path=path).init()
    env = {"PYTHONPATH": str(ROOT / "src"), "HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    n = 12
    procs = [subprocess.Popen([PY, "-c", WRITER, str(path), tag, str(n)], env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for tag in ("a", "b", "c")]
    for p in procs:
        _, err = p.communicate(timeout=180)
        assert p.returncode == 0, err
    t = Tracker(path=path)
    ids = {j["JobID"] for j in t.list_jobs()}
    assert ids == {f"{tag}{i}" for tag in "abc" for i in range(n)}
    assert len(t.list_action_items()) == 3 * n
