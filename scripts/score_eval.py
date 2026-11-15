#!/usr/bin/env python3
"""Eval set for score-job: run it headless on golden postings and check decision + fit band (L-030).

Run by hand (needs `claude`; not in pytest/CI):  .venv/bin/python scripts/score_eval.py [--only NAME ...]
Each tests/fixtures/score_eval/<name>.json is {"expect": {decision?, fit?: [lo, hi], fails?: [...]}, "posting": {...}}.
It scores them in a throwaway copy of the fictional examples/ candidate, never the real profile, and prints one
PASS/FAIL line per job. Exit 1 if any fail. pytest covers `compare` and the fixtures (tests/test_score_eval.py).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests" / "fixtures" / "score_eval"


def load_cases(d: Path = CASES) -> list[tuple[str, dict]]:
    return [(p.stem, json.loads(p.read_text(encoding="utf-8"))) for p in sorted(d.glob("*.json"))]


def compare(expect: dict, score: dict | None) -> list[str]:
    """Problems with a score.json against its expectation; empty = pass."""
    if not score:
        return ["no score.json"]
    out = []
    if expect.get("decision") and score.get("decision") != expect["decision"]:
        out.append(f"decision {score.get('decision')} != {expect['decision']}")
    if expect.get("fit"):
        lo, hi = expect["fit"]
        if not (isinstance(score.get("fit"), int) and lo <= score["fit"] <= hi):
            out.append(f"fit {score.get('fit')} not in {lo}-{hi}")
    out += [f"hard_filter_fails missing {f}" for f in expect.get("fails") or []
            if f not in (score.get("hard_filter_fails") or [])]
    return out


def make_root() -> Path:
    import yaml

    tmp = Path(tempfile.mkdtemp(prefix="score-eval-"))
    for sub in ("config", "profile"):
        shutil.copytree(ROOT / "examples" / sub, tmp / sub)
    shutil.copytree(ROOT / ".claude" / "skills", tmp / ".claude" / "skills")
    (tmp / ".venv").symlink_to(ROOT / ".venv" if (ROOT / ".venv").exists() else Path(sys.prefix))
    pl = tmp / "config" / "pipeline.yaml"
    cfg = yaml.safe_load(pl.read_text())
    cfg["paths"]["tracker_xlsx"] = "JobTracker.xlsx"
    pl.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return tmp


def run_case(root: Path, posting: dict, timeout: int) -> dict | None:
    sys.path.insert(0, str(ROOT / "src"))
    from careeros.config import Settings
    from careeros.runs.config import load_runs_config
    from careeros.runs.headless import build_command

    job = root / "data" / "jobs" / posting["job_id"]
    job.mkdir(parents=True, exist_ok=True)
    (job / "posting.json").write_text(json.dumps(posting, indent=2))
    cmd = build_command(load_runs_config(Settings.load(root)), f"/score-job data/jobs/{posting['job_id']}",
                        kind="score")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}  # the shared .venv may point at another checkout
    try:
        subprocess.run(cmd, cwd=root, env=env, timeout=timeout, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        return None
    f = job / "score.json"
    return json.loads(f.read_text()) if f.exists() else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="*", help="case names (file stems) to run")
    ap.add_argument("--timeout", type=int, default=600, help="seconds per job")
    ap.add_argument("--keep", action="store_true", help="keep the temp root (prints its path)")
    a = ap.parse_args(argv)
    if not shutil.which("claude"):
        print("score_eval: `claude` not on PATH", file=sys.stderr)
        return 2
    root, failed = make_root(), 0
    for name, case in load_cases():
        if a.only and name not in a.only:
            continue
        sc = run_case(root, case["posting"], a.timeout)
        problems = compare(case["expect"], sc)
        failed += bool(problems)
        got = f"decision={sc.get('decision')} fit={sc.get('fit')} fails={sc.get('hard_filter_fails')}" if sc else "-"
        print(f"{'FAIL' if problems else 'PASS'} {name}: {got}" + (f"  ({'; '.join(problems)})" if problems else ""))
    print(f"root kept: {root}" if a.keep else "", end="\n" if a.keep else "")
    if not a.keep:
        shutil.rmtree(root, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
