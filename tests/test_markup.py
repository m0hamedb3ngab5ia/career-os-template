"""Unit tests for careeros.markup: the `**bold**` markup allowed inside profile bullet text."""
from __future__ import annotations

import pytest

from careeros.markup import bold_spans, strip_bold, validate_bold, has_markdown_bold

pytestmark = pytest.mark.unit

MARKED = "Audited **312** SQL controls in **Oracle SQL Developer** using **AWS Athena**"


def test_strip_bold_removes_markers_only():
    assert strip_bold(MARKED) == "Audited 312 SQL controls in Oracle SQL Developer using AWS Athena"
    assert strip_bold("no markers, 5*3 = 15") == "no markers, 5*3 = 15"   # a single * is text
    assert strip_bold("") == "" and strip_bold(None) == ""
    assert strip_bold("**unbalanced") == "unbalanced"                    # never leaks a marker, even when invalid


def test_bold_spans_in_order():
    assert bold_spans(MARKED) == ["312", "Oracle SQL Developer", "AWS Athena"]
    assert bold_spans("plain text") == []
    assert bold_spans("**~40%** of reports") == ["~40%"]


def test_bold_spans_rejects_invalid_markup():
    with pytest.raises(ValueError, match="unbalanced"):
        bold_spans("Built **FastAPI service")


@pytest.mark.parametrize("text", [MARKED, "plain", "", "**x**", "a **b** c **d e** f", "5*3 **x**"])
def test_validate_bold_accepts(text):
    assert validate_bold(text) is None


@pytest.mark.parametrize("text,why", [
    ("Built **FastAPI service", "unbalanced"),
    ("**a** and **b", "unbalanced"),
    ("empty **** span", "empty"),
    ("empty ** ** span", "empty"),
    ("**a **nested** b**", "space"),        # flat markup: nesting shows up as spans with edge spaces
    ("***triple***", "***"),
    ("** leading** space", "space"),
    ("trailing **space ** here", "space"),
])
def test_validate_bold_rejects(text, why):
    err = validate_bold(text)
    assert err is not None and why in err, err


def test_validate_bold_non_string():
    assert validate_bold(None) is None and validate_bold(42) is None


@pytest.mark.parametrize("text,expected", [("Built **FastAPI** services", True), ("**Python**, SQL", True),
                                           ("accepts *args and **kwargs", False), ("2**32 and 2**64", False),
                                           ("plain text", False)])
def test_has_markdown_bold(text: str, expected: bool) -> None:
    assert has_markdown_bold(text) is expected


@pytest.mark.parametrize("text", ["Built **REST API**s for billing", "served **10**k users", "**5**th place",
                                  "x**Python** scripts", "Built a **FastAPI service", "shipped **about 2 months** in",
                                  "**abc**def"])
def test_has_markdown_bold_catches_glued_and_lone_markers(text: str) -> None:
    assert has_markdown_bold(text) is True


@pytest.mark.parametrize("text", ["f(**kwargs, **opts)", "2**n + 3**m", "accepts *args and **kwargs",
                                  "2**32 and 2**64", "x = y**2"])
def test_has_markdown_bold_ignores_code(text: str) -> None:
    assert has_markdown_bold(text) is False
