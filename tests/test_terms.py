"""Unit tests for careeros.terms (shared term matching, moved from qa)."""
import pytest

from careeros import qa
from careeros.terms import term_hit, term_in_text, term_variants

pytestmark = pytest.mark.unit


def test_whole_term_case_insensitive():
    assert term_in_text("go", "I write Go daily")
    assert not term_in_text("go", "data governance")
    assert term_in_text("C++", "c++ and rust")
    assert term_in_text("Next.js", "built with next.js.")


def test_variants_and_hit():
    assert term_variants("Ci-Cd") == {"ci-cd", "ci cd"}
    assert term_variants("CI CD") == {"ci cd", "cicd"}
    assert term_hit("CI-CD", "own the ci cd pipeline")
    assert term_hit("Node.js", "nodejs services")
    assert not term_hit("Rust", "trusty tools")


def test_qa_reuses_shared_matcher():
    assert qa._term_in_text is term_in_text
