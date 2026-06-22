"""Tests for the RAG context-retrieval priority logic (app/retrieval.py)."""

import pytest

from app.retrieval import (
    Candidate,
    PRIORITY,
    extract_join_tables,
    extract_keywords,
    extract_tables_from_sql,
    merge_candidates,
)


# --- merge / priority -------------------------------------------------------


def test_higher_priority_source_wins_on_duplicate_table():
    cands = [
        Candidate("visits", "keyword"),
        Candidate("visits", "semantic", score=0.9),
        Candidate("visits", "relationship"),
    ]
    merged = merge_candidates(cands, limit=10)
    assert len(merged) == 1
    assert merged[0].table == "visits"
    assert merged[0].source == "semantic"  # P1 beats P3/P4


def test_results_ordered_by_priority_then_score():
    cands = [
        Candidate("d", "relationship"),
        Candidate("c", "keyword"),
        Candidate("b", "example", score=0.4),
        Candidate("a", "semantic", score=0.5),
    ]
    merged = merge_candidates(cands, limit=10)
    assert [c.table for c in merged] == ["a", "b", "d", "c"]
    assert [c.source for c in merged] == ["semantic", "example", "relationship", "keyword"]


def test_within_priority_higher_similarity_first():
    cands = [
        Candidate("low", "semantic", score=0.2),
        Candidate("high", "semantic", score=0.95),
        Candidate("mid", "semantic", score=0.5),
    ]
    merged = merge_candidates(cands, limit=10)
    assert [c.table for c in merged] == ["high", "mid", "low"]


def test_limit_truncates_after_ranking():
    cands = [
        Candidate("kw", "keyword"),
        Candidate("sem", "semantic", score=0.9),
        Candidate("ex", "example", score=0.8),
    ]
    merged = merge_candidates(cands, limit=2)
    assert [c.table for c in merged] == ["sem", "ex"]


def test_priority_ordering_constants():
    assert PRIORITY["semantic"] < PRIORITY["example"] < PRIORITY["relationship"] < PRIORITY["keyword"]


def test_unknown_source_rejected():
    with pytest.raises(ValueError):
        Candidate("t", "bogus")


def test_empty_candidates():
    assert merge_candidates([], limit=5) == []


# --- table extraction from SQL ---------------------------------------------


def test_extract_tables_from_join_and_from():
    sql = "SELECT * FROM patients p JOIN visits v ON v.patient_id = p.patient_id"
    assert extract_tables_from_sql(sql) == {"patients", "visits"}


def test_extract_tables_handles_schema_and_quotes_and_case():
    assert extract_tables_from_sql("select * from public.Patients") == {"patients"}
    assert extract_tables_from_sql('SELECT * FROM "Visits"') == {"visits"}


def test_extract_tables_multiple_joins():
    sql = (
        "SELECT * FROM visits v "
        "JOIN departments dep ON dep.department_id = v.department_id "
        "JOIN doctors d ON d.doctor_id = v.doctor_id"
    )
    assert extract_tables_from_sql(sql) == {"visits", "departments", "doctors"}


def test_extract_tables_empty():
    assert extract_tables_from_sql("") == set()


# --- join-annotation parsing -----------------------------------------------


def test_extract_join_tables_parses_annotation():
    ddl = "CREATE TABLE visits (...);\n-- Joins: patients, doctors, departments\n"
    assert extract_join_tables(ddl) == ["patients", "doctors", "departments"]


def test_extract_join_tables_singular_and_dedup():
    ddl = "-- Join: visits\n-- Joins: visits, diagnoses\n"
    assert extract_join_tables(ddl) == ["visits", "diagnoses"]


def test_extract_join_tables_none():
    assert extract_join_tables("CREATE TABLE x (id int);") == []


# --- keyword extraction -----------------------------------------------------


def test_extract_keywords_drops_stopwords_both_languages():
    kws = extract_keywords("How many patients are there?")
    assert "patients" in kws
    assert "how" not in kws and "many" not in kws and "there" not in kws

    kws_es = extract_keywords("¿Cuántos pacientes hay?")
    assert "pacientes" in kws_es
    assert "cuantos" not in kws_es and "hay" not in kws_es
