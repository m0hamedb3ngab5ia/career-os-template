"""Ashby application form (non-user GraphQL) -> normalized fields -> fill_plan (recorded fixture, no network)."""
from __future__ import annotations

import pytest
import yaml
from conftest import EXAMPLE_REPO, load_fixture

from careeros.apply import gh_fill
from careeros.apply.ashby_schema import build_plan, fetch_form, normalize
from careeros.apply.questions import clear_cache

pytestmark = pytest.mark.unit

DATA = load_fixture("ashby/application_form.json")
ANSWERS = EXAMPLE_REPO / "profile" / "standard_answers.yaml"
PROFILE = yaml.safe_load((EXAMPLE_REPO / "profile" / "master.yaml").read_text())
P = "aaaa0000-0000-0000-0000-00000000000"


@pytest.fixture(autouse=True)
def _clear():
    clear_cache()


def _by_id(fields):
    return {f["field_id"]: f for f in fields}


def _plan(**kw):
    files = {"resume": "/tmp/r.pdf", "cover_letter": None}
    return build_plan(normalize(DATA), profile=PROFILE, answers_path=ANSWERS, company="Acme", files=files, **kw)


def test_normalize_types_keep_order():
    fields = normalize(DATA)
    f = _by_id(fields)
    assert [x["field_id"] for x in fields][:3] == ["_systemfield_name", "_systemfield_email", P + "1"]
    assert f["_systemfield_name"]["type"] == "text" and f["_systemfield_name"]["required"]
    assert f["_systemfield_location"]["type"] == "location"
    assert f["_systemfield_resume"]["type"] == "file"
    assert f[P + "2"]["type"] == "boolean" and f[P + "2"]["options"] == ["Yes", "No"]
    assert f[P + "4"]["type"] == "date"
    assert f[P + "5"]["type"] == "textarea" and not f[P + "5"]["required"]
    assert f[P + "7"]["type"] == "checkbox_group" and f[P + "7"]["options"] == ["Remote - US", "NYC"]
    assert f[P + "8"]["type"] == "select"


def test_plan_identity_and_files():
    f = _by_id(_plan()["fields"])
    ident = PROFILE["identity"]
    assert f["_systemfield_name"]["value"] == ident["name"] and f["_systemfield_name"]["source"] == "profile"
    assert f["_systemfield_email"]["value"] == ident["email"]
    assert f[P + "1"]["value"] == ident["phone"]
    assert f["_systemfield_resume"]["value"] == "/tmp/r.pdf" and f["_systemfield_resume"]["source"] == "file"


def test_plan_booleans_use_standard_answers_and_pause_unknowns():
    plan = _plan()
    f = _by_id(plan["fields"])
    assert f[P + "2"]["value"] in ("Yes", "No") and f[P + "2"]["source"].startswith("standard:")
    assert f[P + "3"]["value"] in ("Yes", "No")
    start = f[P + "4"]  # nothing stored for a start date: required, so the user answers
    assert start["value"] is None and start["needs_review"]
    assert any("start a new role" in p for p in gh_fill.plan_problems(plan)) or start["value"]


def test_plan_consent_checkbox_stays_blank_and_does_not_block():
    plan = _plan()
    ack = _by_id(plan["fields"])[P + "6"]
    assert ack["value"] is None
    assert all("Arbitration" not in p for p in gh_fill.plan_problems(plan))
    assert any(f["field_id"] == P + "6" for f in gh_fill.consent_fields(plan))


def test_optional_essay_without_draft_is_skipped_not_blocking():
    f = _by_id(_plan()["fields"])[P + "5"]
    assert f["value"] is None and not f["required"]


def test_fetch_form_posts_graphql(monkeypatch):
    seen = {}

    class R:
        status_code = 200

        def json(self):
            return DATA

        def raise_for_status(self):
            pass

    def post(url, json=None, **kw):
        seen.update(url=url, vars=json["variables"])
        return R()

    monkeypatch.setattr("careeros.apply.ashby_schema.requests.post", post)
    assert fetch_form("acme", "job-1") == DATA
    assert "non-user-graphql" in seen["url"]
    assert seen["vars"] == {"organizationHostedJobsPageName": "acme", "jobPostingId": "job-1"}


def test_plan_adds_eeo_survey_rows_from_standard_answers():
    f = _by_id(_plan()["fields"])
    g = f["_systemfield_eeoc_gender"]
    assert g["type"] == "eeo" and g["value"] == "gender" and g["source"] == "eeo" and not g["needs_review"]
    assert f["_systemfield_eeoc_race"]["value"] == "race_ethnicity" and "race_ethnicity" in f["_systemfield_eeoc_race"]["eeo"]
    assert f["_systemfield_eeoc_veteran_status"]["value"] == "veteran"


def test_fill_one_eeo_checks_the_matching_radio():
    from unittest.mock import MagicMock
    from careeros.apply import ashby_fill
    root = MagicMock()
    w = root.locator.return_value
    w.locator.return_value.all_inner_texts.return_value = ["Race", "Hispanic or Latino", "White (Not Hispanic or Latino)"]
    w.get_by_label.return_value.is_checked.return_value = True
    row = {"field_id": "_systemfield_eeoc_race", "type": "eeo", "value": "race_ethnicity",
           "eeo": {"race_ethnicity": {"answer": "White", "match_not": ["Hispanic"]}}}
    assert ashby_fill.fill_one(root, row)
    w.get_by_label.assert_called_with("White (Not Hispanic or Latino)", exact=True)
