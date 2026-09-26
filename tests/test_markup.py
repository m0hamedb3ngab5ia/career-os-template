"""Unit tests for careeros.markup: the `**bold**` markup allowed inside profile bullet text."""
from __future__ import annotations

import re

import pytest
from conftest import load_script

from careeros.markup import bold_allowed_at, bold_spans, format_path, has_markdown_bold, iter_fields, strip_bold, validate_bold

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
                                           ("accepts f(*args, **kwargs)", True), ("2**32 and 2**64", False),
                                           ("plain text", False)])
def test_has_markdown_bold(text: str, expected: bool) -> None:
    assert has_markdown_bold(text) is expected


@pytest.mark.parametrize("text", ["Built **REST API**s for billing", "served **10**k users", "**5**th place",
                                  "x**Python** scripts", "Built a **FastAPI service", "shipped **about 2 months** in",
                                  "**abc**def"])
def test_has_markdown_bold_catches_glued_and_lone_markers(text: str) -> None:
    assert has_markdown_bold(text) is True


@pytest.mark.parametrize("text", ["2**32 and 2**64", "a 10**6 speedup", "x = 2 ** 10"])
def test_has_markdown_bold_ignores_numeric_powers(text: str) -> None:
    assert has_markdown_bold(text) is False


@pytest.mark.parametrize("text", ["f(**kwargs, **opts)", "{**a, **b}", "x = y**2", "Tools: Go, **Python and Kafka.",
                                  "I used SQL, **Kafka, and Python.", "We shipped it (**FastAPI) in May.",
                                  "Built **REST API**s", "The ** sign"])
def test_any_other_double_star_counts(text: str) -> None:
    # strict on purpose: code with ** in an answer is a visible false alarm; a pasted bullet marker is not visible
    assert has_markdown_bold(text) is True


@pytest.mark.parametrize("text", ["I built **python services", "shipped **about 2 months in",
                                  "I cut **manual prep by 5 hours", "led **ci/cd migration"])
def test_lone_lowercase_marker_is_bold_not_code(text: str) -> None:
    assert has_markdown_bold(text) is True


# --- where `**` may appear: one table for doctor (master.yaml paths) and render.py (resume.json paths) ---------

# (master.yaml key tuple, allowed in master.yaml, resume.json key tuple it becomes, allowed in resume.json).
# Tuples, not dotted strings, so keys holding "." or "[" (long.v2, alt[1]) are covered the way the live code sees them.
E = ("experience", 0, "bullets", 2)
BOLD_PATHS = [
    ((*E, "text"), True, (*E, "text"), True),
    (("projects", 1, "bullets", 0, "text"), True, ("projects", 1, "bullets", 0, "text"), True),
    (("leadership", 0, "bullets", 0, "text"), True, ("leadership", 0, "bullets", 0, "text"), True),
    ((*E, "variants", "short"), True, (*E, "text"), True),
    ((*E, "variants", 1), True, (*E, "text"), True),
    ((*E, "variants", "long.v2"), True, (*E, "text"), True),
    ((*E, "variants", "alt[1]"), True, (*E, "text"), True),
    (("summary_variants", "general"), True, ("summary",), True),
    (("summary_variants", "backend.v2"), True, ("summary",), True),
    (("skills", "programming", 0), False, ("skills", "programming", 0), False),
    (("skills", "lang.v2", 0), False, ("skills", "lang.v2", 0), False),
    (("experience", 0, "title"), False, ("experience", 0, "title"), False),
    (("experience", 0, "stack", 1), False, ("experience", 0, "stack", 1), False),
    ((*E, "id"), False, (*E, "id"), False),
    (("projects", 0, "name"), False, ("projects", 0, "name"), False),
    (("education", 0, "degree"), False, ("education", 0, "degree"), False),
    (("identity", "name"), False, ("identity", "name"), False),
    (("skills", "text"), False, ("skills", "text"), False),
]


def _tree(keys: tuple) -> dict:
    """A minimal tree with "**x**" at `keys`."""
    root: dict = {}
    node: object = root
    for i, k in enumerate(keys):
        last = i == len(keys) - 1
        child = "**x**" if last else ([] if isinstance(keys[i + 1], int) else {})
        if isinstance(k, int):
            node.extend([{}] * (k + 1 - len(node)))  # type: ignore[union-attr]
            node[k] = child  # type: ignore[index]
        else:
            node[k] = child  # type: ignore[index]
        node = child
    return root


@pytest.mark.parametrize("master_keys, in_master, resume_keys, in_resume", BOLD_PATHS)
def test_bold_allowed_table(master_keys, in_master, resume_keys, in_resume):
    assert bold_allowed_at(master_keys, "master") is in_master
    assert bold_allowed_at(resume_keys, "resume") is in_resume


@pytest.mark.parametrize("master_keys, in_master, resume_keys, in_resume", BOLD_PATHS)
def test_render_check_bold_agrees_with_table(master_keys, in_master, resume_keys, in_resume):
    render = load_script("templates/resume/render.py")
    assert (render.check_bold(_tree(resume_keys)) == []) is in_resume


@pytest.mark.parametrize("master_keys, in_master, resume_keys, in_resume", BOLD_PATHS)
def test_doctor_check_bold_agrees_with_table(master_keys, in_master, resume_keys, in_resume):
    from careeros.doctor import FAIL, check_bold
    fails = [c for c in check_bold(_tree(master_keys)) if c.level == FAIL]
    assert (not fails) is in_master, fails


def test_iter_fields_and_format_path():
    got = list(iter_fields({"a": ["x", {"b.c": "y", 3: "z"}], "n": 1, "c": None}))
    assert got == [(("a", 0), "x"), (("a", 1, "b.c"), "y"), (("a", 1, 3), "z")]
    assert format_path(("a", 1, "b.c")) == "a[1].b.c"


@pytest.mark.parametrize("keys,source,expected", [
    (("summary_variants", "backend.v2"), "master", True),
    (("experience", 0, "bullets", 2, "variants", "long.v2"), "master", True),
    (("experience", 0, "bullets", 2, "variants", "alt[1]"), "master", True),
    (("experience", 0, "bullets", 2, "text"), "master", True),
    (("experience", 0, "bullets", 2, "id"), "master", False),
    (("skills", "lang.v2", 0), "master", False),
    (("summary",), "resume", True),
    (("projects", 1, "bullets", 0, "text"), "resume", True),
    (("projects", 1, "bullets", 0, "variants", "short"), "resume", False),
])
def test_bold_allowed_at_is_structural(keys, source, expected):
    assert bold_allowed_at(keys, source) is expected
