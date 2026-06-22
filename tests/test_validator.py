"""Tests for the read-only SQL validator (app/validator.py).

These prove the validator blocks writes / DDL / privilege / multi-statement /
data-modifying-CTE / filesystem-function attacks while allowing legitimate
read-only SELECT queries — including ones that merely *contain* scary words
inside string literals or comments.
"""

import pytest

from app.validator import (
    SQLValidationError,
    is_read_only,
    validate_read_only,
)

# --- queries that MUST be allowed ------------------------------------------

ALLOWED = [
    "SELECT 1",
    "select count(*) from patients",
    "SELECT COUNT(*) AS total_patients FROM patients",
    "SELECT * FROM patients WHERE city = 'Springfield'",
    "SELECT p.full_name, v.visit_date FROM patients p JOIN visits v ON v.patient_id = p.patient_id",
    "SELECT code, COUNT(*) FROM diagnoses GROUP BY code ORDER BY COUNT(*) DESC LIMIT 5",
    "WITH recent AS (SELECT * FROM visits) SELECT COUNT(*) FROM recent",
    "SELECT COUNT(*) FROM visits WHERE date_trunc('month', visit_date) = date_trunc('month', CURRENT_DATE)",
    "SELECT 1;",                          # single trailing semicolon is fine
    "  SELECT 1  ",                       # surrounding whitespace
    "-- a leading comment\nSELECT 1",     # leading line comment
    "/* block */ SELECT 1",               # leading block comment
    "(SELECT 1) UNION (SELECT 2)",        # parenthesised / set operation
    "SELECT replace(full_name, 'a', 'b') FROM patients",   # REPLACE() is a function
    "SELECT * FROM visits FETCH FIRST 5 ROWS ONLY",        # FETCH FIRST is standard LIMIT
    "SELECT * FROM patients OFFSET 10",                    # OFFSET is fine
    "SELECT name FROM patients WHERE note = 'Robert; DROP TABLE students'",  # injection lives in a literal
    "SELECT 'DELETE everything' AS warning",               # keyword inside a string
    "SELECT created_at FROM sql_feedback",                 # column substring 'create' must not trip
]

# --- queries that MUST be rejected -----------------------------------------

BLOCKED = [
    "",                                       # empty
    "   ",                                     # whitespace only
    "INSERT INTO patients (full_name) VALUES ('x')",
    "UPDATE patients SET city = 'x'",
    "DELETE FROM patients",
    "DROP TABLE patients",
    "ALTER TABLE patients ADD COLUMN x int",
    "CREATE TABLE evil (id int)",
    "TRUNCATE patients",
    "GRANT SELECT ON patients TO bob",
    "REVOKE SELECT ON patients FROM bob",
    "EXEC sp_who",
    "EXECUTE some_plan",
    "SELECT 1; DROP TABLE patients",          # stacked / multi-statement
    "SELECT 1; SELECT 2",                      # multiple statements, even if both reads
    "WITH x AS (DELETE FROM patients RETURNING *) SELECT * FROM x",  # data-modifying CTE
    "SELECT * INTO new_table FROM patients",   # SELECT ... INTO creates a table
    "EXPLAIN ANALYZE SELECT 1",                # EXPLAIN ANALYZE can execute writes
    "COPY patients TO '/tmp/out.csv'",
    "VACUUM patients",
    "SET ROLE postgres",
    "BEGIN; SELECT 1; COMMIT",
    "SELECT pg_read_file('/etc/passwd')",      # dangerous function
    "SELECT pg_sleep(10)",                     # DoS function
    "MERGE INTO patients USING staging ON true WHEN MATCHED THEN DELETE",
]


@pytest.mark.parametrize("sql", ALLOWED)
def test_allows_read_only(sql):
    # should not raise, and should report read-only
    cleaned = validate_read_only(sql)
    assert isinstance(cleaned, str) and cleaned
    assert not cleaned.endswith(";")
    assert is_read_only(sql) is True


@pytest.mark.parametrize("sql", BLOCKED)
def test_blocks_unsafe(sql):
    with pytest.raises(SQLValidationError):
        validate_read_only(sql)
    assert is_read_only(sql) is False


def test_trailing_semicolon_is_stripped():
    assert validate_read_only("SELECT 1;") == "SELECT 1"
    assert validate_read_only("SELECT 1 ;  ") == "SELECT 1"


def test_comment_preserving_return_value():
    # Comments are allowed; the executed SQL keeps them (only trailing ; removed)
    out = validate_read_only("SELECT 1 -- trailing comment\n")
    assert "SELECT 1" in out


def test_error_messages_are_specific():
    with pytest.raises(SQLValidationError, match="(?i)multiple statements"):
        validate_read_only("SELECT 1; SELECT 2")
    with pytest.raises(SQLValidationError, match="(?i)forbidden keyword"):
        validate_read_only("WITH x AS (DELETE FROM patients RETURNING *) SELECT * FROM x")
    with pytest.raises(SQLValidationError, match="(?i)only select"):
        validate_read_only("UPDATE patients SET city = 'x'")
