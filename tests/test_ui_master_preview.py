"""REQ-151: Profile shows the master résumé itself (GET /api/profile/master.pdf, inline, read-only)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from conftest import make_temp_root
from fastapi.testclient import TestClient
from fixtures.ui_data import build_ui_data

from careeros import resumes
from careeros.ui.app import create_app
from careeros.ui.index import Index
from careeros.ui.security import LOOPBACK

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture
def app_root(tmp_path):
    d = build_ui_data(make_temp_root(tmp_path / "repo"), NOW)
    ix = Index(d["settings"])
    ix.rebuild()
    app = create_app(d["settings"], index=ix, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=tmp_path / "no-static", now=lambda: NOW)
    with TestClient(app) as c:
        yield c, d["settings"].root
    ix.close()


def test_master_pdf_is_served_inline(app_root):
    c, root = app_root
    resumes.add(root, "cv.pdf", PDF, name="Master")
    r = c.get("/api/profile/master.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    assert r.content == PDF


def test_no_master_is_404(app_root):
    c, _ = app_root
    assert c.get("/api/profile/master.pdf").status_code == 404


def test_docx_master_is_409(app_root):
    c, root = app_root
    resumes.add(root, "cv.docx", b"PK\x03\x04" + b"\0" * 64, name="Master")
    r = c.get("/api/profile/master.pdf")
    assert r.status_code == 409 and "isn't a PDF" in r.json()["detail"]


def test_refused_render_is_409(app_root, monkeypatch):
    c, root = app_root
    resumes.add(root, "cv.pdf", PDF, name="Master")

    def refuse(*_a, **_k):
        raise resumes.Refused("no LaTeX engine installed")
    monkeypatch.setattr(resumes, "download_name", refuse)
    r = c.get("/api/profile/master.pdf")
    assert r.status_code == 409 and "LaTeX" in r.json()["detail"]
