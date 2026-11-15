"""`careeros view`: the three sections render from disk and all text is escaped."""
from __future__ import annotations

import pytest

from careeros import view
from careeros.config import get_settings
from careeros.models import Posting
from careeros.store import Store

pytestmark = [pytest.mark.unit, pytest.mark.readiness]


def test_view_sections_and_escaping(temp_root):
    store = Store(get_settings(temp_root))
    p = Posting(job_id="j1", company="<script>alert(1)</script> & Co", title="Eng", location="x", ats="greenhouse",
                url="https://e.test/1", description="d", fetched_at="2026-01-01T00:00:00Z")
    store.save_posting(p)
    store.set_status("j1", "applied")
    out = view.write(temp_root)
    assert out == temp_root / "data" / "views" / "status.html"
    page = out.read_text(encoding="utf-8")
    assert "Onboarding checklist" in page
    assert "todo: Master résumé set" in page
    assert "<h2>Pipeline</h2>" in page and "<td>applied</td>" in page
    assert "Applied (newest first" in page and "&lt;script&gt;alert(1)&lt;/script&gt; &amp; Co" in page
    assert "<script" not in page
