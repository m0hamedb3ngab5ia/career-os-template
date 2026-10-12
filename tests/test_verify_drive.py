"""verify-careeros drive.py: step log numbering, clicks and file names carry across sessions (fake Playwright)."""
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
SKILL = Path(__file__).resolve().parents[1] / ".claude/skills/verify-careeros"


class _Page:
    url = "http://127.0.0.1:8799/x"

    def wait_for_selector(self, *a, **k): pass
    def wait_for_load_state(self, *a): pass
    def screenshot(self, path): Path(path).write_bytes(b"png")


class _Tracing:
    def start(self, **k): pass
    def stop(self, path): Path(path).write_bytes(b"zip")


class _Ctx:
    tracing = _Tracing()
    def new_page(self): return _Page()
    def close(self): pass


class _PW:
    def __init__(self, seen): self.chromium, self.seen = self, seen
    def launch(self, **k): return self
    def new_context(self, **k): self.seen.update(k); return _Ctx()
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass


@pytest.fixture
def drive(monkeypatch):
    seen = {}
    api = types.ModuleType("playwright.sync_api")
    api.sync_playwright = lambda: _PW(seen)
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", api)
    monkeypatch.syspath_prepend(str(SKILL))
    sys.modules.pop("drive", None)
    mod = importlib.import_module("drive")
    yield mod, seen
    sys.modules.pop("drive", None)


def test_numbering_clicks_and_traces_continue_across_sessions(drive, tmp_path):
    mod, seen = drive
    with mod.session(tmp_path) as (page, step):
        step("open", lambda: None, "text=x")
        step("upload file", lambda: None, click=True)
    with mod.session(tmp_path) as (page, step):
        step("reload", lambda: None, click=True)
    recs = [json.loads(l) for l in (tmp_path / "steps.jsonl").read_text().splitlines()]
    assert [r["step"] for r in recs] == [1, 2, 3]
    assert [r["clicks"] for r in recs] == [0, 1, 2]
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["01-open.png", "02-upload_file.png", "03-reload.png", "steps.jsonl", "trace-02.zip", "trace-03.zip"]
    assert seen["base_url"] == "http://127.0.0.1:8799"
