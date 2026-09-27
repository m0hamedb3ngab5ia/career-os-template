"""`careeros ui` entry points without a real server: the missing-extra message and serve()'s browser opening."""
from __future__ import annotations

import builtins

import pytest
from conftest import make_temp_root

from careeros import cli
from careeros.config import Settings

pytestmark = pytest.mark.unit


def test_cmd_ui_without_the_extra_says_how_to_install(monkeypatch, capsys, tmp_path):
    real = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "fastapi":
            raise ImportError("No module named 'fastapi'", name="fastapi")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    root = make_temp_root(tmp_path / "repo")
    assert cli.main(["--root", str(root), "ui", "--no-open"]) == 1
    err = capsys.readouterr().err
    assert "fastapi" in err and '.[ui]' in err


@pytest.fixture
def fake_run(monkeypatch):
    import threading

    import uvicorn

    from careeros.ui import server
    from careeros.ui.watch import Watcher

    calls = {"run": [], "opened": []}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls["run"].append(kw))
    monkeypatch.setattr(Watcher, "start", lambda self: None)
    monkeypatch.setattr(Watcher, "stop", lambda self: None)

    class Timer:
        def __init__(self, delay, fn, args=()):
            self.fn, self.args = fn, args

        def start(self):
            self.fn(*self.args)

    monkeypatch.setattr(server.threading, "Timer", Timer)
    monkeypatch.setattr(server.webbrowser, "open", lambda url: calls["opened"].append(url))
    assert threading  # the real module stays untouched outside server
    return calls


@pytest.fixture
def settings(tmp_path):
    return Settings.load(make_temp_root(tmp_path / "repo"))


def test_serve_opens_the_browser_by_default(fake_run, settings):
    from careeros.ui.server import serve

    assert serve(settings) == 0
    assert fake_run["opened"] == ["http://127.0.0.1:8765"]
    assert fake_run["run"] == [{"host": "127.0.0.1", "port": 8765, "log_level": "warning"}]


def test_serve_no_open(fake_run, settings):
    from careeros.ui.server import serve

    assert serve(settings, open_browser=False, port=9001) == 0
    assert fake_run["opened"] == [] and fake_run["run"][0]["port"] == 9001


def test_serve_ipv6_loopback_url(fake_run, settings):
    from careeros.ui.server import serve

    assert serve(settings, host="::1") == 0
    assert fake_run["opened"] == ["http://[::1]:8765"]


def test_serve_open_browser_false_in_config(fake_run, settings):
    from careeros.ui.server import serve

    settings.pipeline["ui"] = {"open_browser": False}
    assert serve(settings) == 0 and fake_run["opened"] == []
