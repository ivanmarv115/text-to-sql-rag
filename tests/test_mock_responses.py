"""Tests for offline/mock mode (app/mock_responses.py).

Crucially this also asserts that every canned SQL string is accepted by the
read-only validator — so mock mode can never ship SQL the safety layer would
reject, and the two modules stay in sync.
"""

import pytest

from app.mock_responses import CANNED, SAMPLE_QUESTIONS, canned_chat, match_sql
from app.validator import validate_read_only


@pytest.mark.parametrize("entry", CANNED, ids=[c.label for c in CANNED])
def test_canned_sql_is_valid_read_only(entry):
    # Should not raise — proves canned SQL is a single read-only SELECT.
    assert validate_read_only(entry.sql)


@pytest.mark.parametrize("question", SAMPLE_QUESTIONS)
def test_sample_questions_all_match(question):
    assert match_sql(question) is not None


@pytest.mark.parametrize(
    "question,expected_label",
    [
        ("How many patients are there?", "Count patients"),
        ("¿Cuántos pacientes hay?", "Count patients"),
        ("How many patients per city?", "Patients per city"),
        ("How many visits happened this month?", "Visits this month"),
        ("What are the most common diagnoses?", "Most common diagnoses"),
        ("How many visits per department?", "Visits per department"),
        ("How many doctors do you have?", "Count doctors"),
    ],
)
def test_specific_routing(question, expected_label):
    match = match_sql(question)
    assert match is not None
    assert match.label == expected_label


def test_unrecognised_question_returns_none():
    assert match_sql("what is the meaning of life?") is None
    assert match_sql("") is None


def test_canned_chat_non_empty():
    assert canned_chat("hello").strip()
    assert canned_chat("anything else").strip()
