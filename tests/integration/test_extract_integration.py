"""`python -m careeros.extract SRC OUT` writes a byte-identical ats.json on every run (E2E-003-01)."""
import json
import subprocess

import pytest
from conftest import PY, subprocess_env
from test_extract import RESUME, make_docx

pytestmark = pytest.mark.integration


def test_cli_writes_ats_json(tmp_path):
    src = make_docx(tmp_path / "r.docx", RESUME.strip().splitlines())
    out = tmp_path / "v1" / "ats.json"
    runs = []
    for _ in range(2):
        r = subprocess.run([PY, "-m", "careeros.extract", str(src), str(out)],
                           capture_output=True, text=True, env=subprocess_env(tmp_path, tmp_path))
        assert r.returncode == 0, r.stderr
        runs.append(out.read_bytes())
    assert runs[0] == runs[1]
    view = json.loads(runs[0])
    assert view["fields"]["contact"]["email"] == "alex@example.com"
    assert view["warnings"] == []
