"""Skill instructions executed as written: the prepare-job cover-letter render step on a temp repo root."""
from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import PY, ROOT, subprocess_env, tectonic_cache

pytestmark = pytest.mark.integration

OFFLINE_ENGINE = bool((shutil.which("tectonic") and tectonic_cache()) or shutil.which("pdflatex"))

LETTER = """---
job_id: job000000001
company: Ledgerline
role: Software Engineer, Backend
team: null
greeting: "Hi Ledgerline team,"
date: 2026-09-25
sign_off: "Alex"
close_variant: "Would like to talk."
facts_used:
  - {fact: "Payments owns the ledger", source: posting}
bullet_ids_used: [acme.1]
narrative_ids_used: []
voice_verified: false
---
Hi Ledgerline team,

At Acme I built a FastAPI service in Python that ingests Kafka order events into PostgreSQL.

Would like to talk.

Alex
"""


def test_prepare_job_cover_letter_step_writes_cover_letter_txt(temp_root: Path, tmp_path: Path):
    text = (ROOT / ".claude" / "skills" / "prepare-job" / "SKILL.md").read_text(encoding="utf-8")
    cmd = re.search(r"`(\.venv/bin/python templates/cover_letter/render\.py JOB/cover_letter\.md[^`]*)`", text).group(1)
    job = temp_root / "data" / "jobs" / "job000000001"
    job.mkdir(parents=True)
    (job / "cover_letter.md").write_text(LETTER)
    argv = shlex.split(cmd.replace("JOB", str(job)))[1:]  # the documented command, run with this interpreter
    if not OFFLINE_ENGINE:
        argv.append("--no-pdf")
    home = tmp_path / "home"
    home.mkdir()
    r = subprocess.run([PY, *argv], cwd=temp_root, env=subprocess_env(temp_root, home), capture_output=True,
                       text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    txt = (job / "cover_letter.txt").read_text()
    assert txt.startswith("Hi Ledgerline team,") and txt.rstrip().endswith("Alex")
    assert (job / "cover_letter.pdf").exists() is OFFLINE_ENGINE
