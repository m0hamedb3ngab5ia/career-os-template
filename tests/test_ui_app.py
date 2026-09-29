"""careeros.ui.app: plain_validation turns FastAPI's validation errors into one plain sentence."""
from __future__ import annotations

import pytest

from careeros.ui.app import plain_validation

pytestmark = pytest.mark.unit


def test_missing_field_skips_the_got_clause_and_never_reprs_the_input():
    """A `missing` error has no input worth showing; the value must not even be repr'd (it can be the
    whole request body, and building that repr is wasted work when the message discards it anyway)."""

    class Boom:
        def __repr__(self) -> str:  # pragma: no cover - must never run
            raise AssertionError("input should not be repr'd for a missing field")

    err = {"loc": ("body", "max_jobs"), "type": "missing", "input": Boom()}
    assert plain_validation([err]) == "max_jobs is required."


def test_present_input_is_shown_and_cut_short():
    err = {"loc": ("body", "max_jobs"), "type": "int_parsing", "input": 2.5}
    assert plain_validation([err]) == "max_jobs must be a whole number, got 2.5."
    long_input = "x" * 200
    err2 = {"loc": ("body", "note"), "type": "string_type", "input": long_input}
    msg = plain_validation([err2])
    assert msg.startswith("note must be text, got '") and msg.endswith("….")
