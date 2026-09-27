"""Concurrent writers and readers of files under the runs dir never see a partial file or crash.

The UI server handles requests on a thread pool and the runner shares a process with its helpers, so two
threads in one process may write the same JSON at once. A temp name keyed only by pid makes them share one
temp file: one thread's rename can publish the other's half-written bytes, and the loser's rename fails.
"""
import json
import logging
import threading
from pathlib import Path

from careeros.runs import store as store_mod
from careeros.runs.atomic import write_json
from careeros.runs.store import RunStore


class _S:
    def __init__(self, root: Path):
        self.paths = {"runs_dir": str(root / "runs"), "jobs_dir": str(root / "jobs")}


def _hammer(write, read, path: Path, writers: int = 6, rounds: int = 150) -> tuple[list, list]:
    errors, bad_reads = [], []
    stop = threading.Event()

    def w(i: int) -> None:
        try:
            for n in range(rounds):
                write({"id": "r1", "writer": i, "n": n, "pad": "x" * (2000 + 37 * i)})
        except Exception as e:  # noqa: BLE001 - the test collects any writer failure
            errors.append(e)

    def r() -> None:
        while not stop.is_set():
            try:
                text = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                continue
            try:
                json.loads(text)
            except json.JSONDecodeError as e:
                bad_reads.append(e)
            got = read()
            if got is None:
                bad_reads.append("reader got None for an existing file")

    ws = [threading.Thread(target=w, args=(i,)) for i in range(writers)]
    rs = [threading.Thread(target=r) for _ in range(2)]
    for t in rs + ws:
        t.start()
    for t in ws:
        t.join()
    stop.set()
    for t in rs:
        t.join()
    return errors, bad_reads


def test_write_json_is_atomic_across_threads(tmp_path: Path):
    p = tmp_path / "x.json"
    errors, bad = _hammer(lambda d: write_json(p, d), lambda: json.loads(p.read_text()), p)
    assert errors == [] and bad == []
    assert not list(tmp_path.glob("*.tmp"))  # no temp files left behind


def test_save_run_and_load_run_survive_concurrent_threads(tmp_path: Path):
    rs = RunStore(_S(tmp_path))
    errors, bad = _hammer(rs.save_run, lambda: rs.load_run("r1"), rs.run_dir("r1") / "run.json")
    assert errors == [] and bad == []
    assert rs.load_run("r1")["id"] == "r1"


def test_pause_writes_survive_concurrent_threads(tmp_path: Path):
    from datetime import datetime, timezone

    rs = RunStore(_S(tmp_path))
    now = datetime.now(timezone.utc)
    errors, bad = _hammer(lambda d: rs.set_pause(None, json.dumps(d), now),
                          lambda: json.loads(rs.pause_path.read_text()), rs.pause_path)
    assert errors == [] and bad == []


def test_corrupt_run_json_is_logged_not_silently_hidden(tmp_path: Path, caplog):
    rs = RunStore(_S(tmp_path))
    p = rs.run_dir("r1") / "run.json"
    p.parent.mkdir(parents=True)
    p.write_text('{"id": "r1", "sta', encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger=store_mod.__name__):
        assert rs.load_run("r1") is None
    assert any("run.json" in r.getMessage() for r in caplog.records)


def test_missing_file_reads_as_none_without_a_warning(tmp_path: Path, caplog):
    rs = RunStore(_S(tmp_path))
    with caplog.at_level(logging.WARNING, logger=store_mod.__name__):
        assert rs.load_run("nope") is None
    assert caplog.records == []
