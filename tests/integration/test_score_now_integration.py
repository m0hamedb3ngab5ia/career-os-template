"""E2E-017-04 / REQ-137: `careeros run score --job X` scores X without ticking it (prepare still ticks, REQ-104)."""
from __future__ import annotations

import pytest

from careeros.config import Settings
from careeros.store import Store

from test_runs_integration import add_jobs, cli, env_for, fake_bin, home, root  # noqa: F401

pytestmark = pytest.mark.integration


def test_run_score_job_does_not_tick_E2E_017_04(root, home, fake_bin, tmp_path):
    ids = add_jobs(root, 2)
    store = Store(Settings.load(root))
    store.set_selected(ids, False)
    env = env_for(root, home, fake_bin)
    r = cli(root, env, "run", "score", "--job", ids[0], "--job", ids[1])
    assert r.returncode == 0, r.stderr
    assert not any(store.is_selected(j) for j in ids)


def test_run_prepare_job_still_ticks_E2E_017_04(root, home, fake_bin):
    ids = add_jobs(root, 1)
    store = Store(Settings.load(root))
    store.set_selected(ids, False)
    cli(root, env_for(root, home, fake_bin), "run", "prepare", "--job", ids[0])
    assert store.is_selected(ids[0])


@pytest.mark.parametrize("kind", ["prepare", "apply"])
def test_run_prepare_apply_reject_repeated_job_E2E_017_04(root, home, fake_bin, kind):
    ids = add_jobs(root, 2)
    store = Store(Settings.load(root))
    store.set_selected(ids, False)
    r = cli(root, env_for(root, home, fake_bin), "run", kind, "--job", ids[0], "--job", ids[1])
    assert r.returncode == 2
    assert "takes one job id" in r.stderr
    assert not store.is_selected(ids[0]) and not store.is_selected(ids[1])
