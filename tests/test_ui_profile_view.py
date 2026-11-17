"""Read-only Profile and Settings views: grouped, plain values, no credentials."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from careeros.ui.services import profile_view  # noqa: E402

pytestmark = pytest.mark.unit


def test_profile_lists_documents_and_answers(example_settings, tmp_path):
    s = example_settings
    s.root = tmp_path
    (tmp_path / "profile" / "documents").mkdir(parents=True)
    (tmp_path / "profile" / "documents" / "transcript.pdf").write_bytes(b"%PDF-1")
    p = profile_view.profile(s)
    assert [d.name for d in p.documents] == ["transcript.pdf"]
    assert p.documents[0].size == 6
    assert p.resumes == []
    assert any(a.key == "work_authorization" for a in p.answers)


def test_settings_grouped_and_no_secrets(example_settings):
    v = profile_view.settings_view(example_settings)
    assert v.sections
    assert all(g.rows for sec in v.sections for g in sec.groups)
    labels = " ".join(r.label.lower() for sec in v.sections for g in sec.groups for r in g.rows)
    assert "credential" not in labels and "password" not in labels
