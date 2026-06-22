"""Defense-in-depth, read-only SQL validation.

This module is deliberately dependency-free (stdlib only) so it can be unit
tested in isolation and reused from both the pipeline layer and the execution
engine. It is one of two independent validation passes; the other safety net
is a database-level read-only role (see ``flyway/clinic``).

The validator answers a single question: *is this string a single, read-only
``SELECT`` statement that is safe to send to the database?* It does **not** try
to fully parse SQL. Instead it:

1. strips comments and the contents of string / quoted-identifier / dollar
   literals, so keywords or semicolons hidden inside them cannot fool it;
2. requires the statement to begin with ``SELECT`` or ``WITH`` (a CTE that
   resolves to a ``SELECT``);
3. rejects multiple statements (stacked queries);
4. rejects any write/DDL/side-effecting keyword anywhere in the statement
   (this also catches data-modifying CTEs such as
   ``WITH x AS (DELETE ... RETURNING *) SELECT ...``).

It is intentionally conservative: when in doubt, reject. The real guarantee is
the read-only database role; this layer keeps obviously-unsafe SQL from ever
reaching the connection.
"""

from __future__ import annotations

import re

__all__ = [
    "SQLValidationError",
    "validate_read_only",
    "is_read_only",
    "FORBIDDEN_KEYWORDS",
]


class SQLValidationError(ValueError):
    """Raised when a SQL string is not a safe, single read-only statement."""


# Statement-type / side-effecting keywords that must never appear in a
# read-only query. None of these collide with common SQL *functions*
# (e.g. ``REPLACE()`` is a string function and is intentionally NOT listed;
# ``set_config`` survives because ``\bSET\b`` will not match across the
# underscore). ``SELECT ... FOR UPDATE`` is caught by ``UPDATE``.
FORBIDDEN_KEYWORDS: frozenset[str] = frozenset(
    {
        # writes
        "INSERT",
        "UPDATE",
        "DELETE",
        "UPSERT",
        "MERGE",
        # DDL
        "CREATE",
        "ALTER",
        "DROP",
        "TRUNCATE",
        "REINDEX",
        "CLUSTER",
        "REFRESH",
        # privileges
        "GRANT",
        "REVOKE",
        # procedural / code execution
        "EXEC",
        "EXECUTE",
        "CALL",
        "DO",
        "PREPARE",
        "DEALLOCATE",
        # data import/export & filesystem
        "COPY",
        "IMPORT",
        # locking / session / maintenance
        "LOCK",
        "VACUUM",
        "SET",
        "RESET",
        "DISCARD",
        # transaction control (stacked-query / side-effect signals)
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT",
        # async / replication
        "LISTEN",
        "NOTIFY",
        "UNLISTEN",
        "ATTACH",
        "DETACH",
        "PRAGMA",
        # SELECT ... INTO creates a table in PostgreSQL
        "INTO",
    }
)

# A handful of dangerous PostgreSQL functions that read/write the filesystem or
# escalate. Blocked as an extra layer even though they are read "queries".
FORBIDDEN_FUNCTIONS: frozenset[str] = frozenset(
    {
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "lo_import",
        "lo_export",
        "dblink",
        "dblink_exec",
        "copy_from",
        "copy_to",
        "pg_sleep",
        "pg_terminate_backend",
    }
)

_LEADING_KEYWORD_RE = re.compile(r"^[\s(]*([A-Za-z_]+)")


def _strip_comments_and_literals(sql: str) -> str:
    """Return ``sql`` with comments removed and the *contents* of string,
    quoted-identifier and dollar-quoted literals blanked out.

    The surrounding quote characters are kept so the result is still
    structurally similar to the input (useful for the leading-keyword and
    semicolon checks), but nothing *inside* a literal or comment can influence
    keyword / statement-boundary detection.
    """
    out: list[str] = []
    i = 0
    n = len(sql)
    state = "normal"  # normal | line_comment | block_comment | single | double | dollar
    dollar_tag = ""
    dollar_re = re.compile(r"\$([A-Za-z_]\w*)?\$")

    while i < n:
        ch = sql[i]
        two = sql[i : i + 2]

        if state == "normal":
            if two == "--":
                state = "line_comment"
                i += 2
                continue
            if two == "/*":
                state = "block_comment"
                i += 2
                continue
            if ch == "'":
                state = "single"
                out.append("'")
                i += 1
                continue
            if ch == '"':
                state = "double"
                out.append('"')
                i += 1
                continue
            m = dollar_re.match(sql, i)
            if m:
                dollar_tag = m.group(0)
                state = "dollar"
                out.append(" ")
                i += len(dollar_tag)
                continue
            out.append(ch)
            i += 1
            continue

        if state == "line_comment":
            if ch == "\n":
                state = "normal"
                out.append("\n")
            i += 1
            continue

        if state == "block_comment":
            if two == "*/":
                state = "normal"
                i += 2
                continue
            i += 1
            continue

        if state == "single":
            if ch == "\\":  # backslash escape (E'' strings)
                i += 2
                continue
            if two == "''":  # standard doubled-quote escape
                i += 2
                continue
            if ch == "'":
                state = "normal"
                out.append("'")
                i += 1
                continue
            i += 1
            continue

        if state == "double":
            if two == '""':
                i += 2
                continue
            if ch == '"':
                state = "normal"
                out.append('"')
                i += 1
                continue
            i += 1
            continue

        if state == "dollar":
            if sql.startswith(dollar_tag, i):
                state = "normal"
                out.append(" ")
                i += len(dollar_tag)
                continue
            i += 1
            continue

    return "".join(out)


def _split_statements(stripped: str) -> list[str]:
    """Split on top-level semicolons (literals already blanked) and drop empties."""
    parts = [p.strip() for p in stripped.split(";")]
    return [p for p in parts if p]


def validate_read_only(sql: str) -> str:
    """Validate that ``sql`` is a single read-only statement.

    Returns the cleaned SQL (trimmed, trailing semicolon removed) ready for
    execution. Raises :class:`SQLValidationError` otherwise.
    """
    if sql is None or not str(sql).strip():
        raise SQLValidationError("Empty SQL.")

    raw = str(sql).strip()
    stripped = _strip_comments_and_literals(raw)

    statements = _split_statements(stripped)
    if len(statements) == 0:
        raise SQLValidationError("No executable statement found.")
    if len(statements) > 1:
        raise SQLValidationError(
            "Multiple statements are not allowed (stacked queries blocked)."
        )

    # Leading keyword must be SELECT or WITH.
    m = _LEADING_KEYWORD_RE.match(stripped)
    head = (m.group(1) if m else "").upper()
    if head not in ("SELECT", "WITH"):
        raise SQLValidationError(
            f"Only SELECT / WITH queries are allowed (got '{head or '?'}')."
        )

    upper = stripped.upper()

    # Forbidden statement-type / side-effecting keywords anywhere in the query.
    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", upper):
            raise SQLValidationError(f"Forbidden keyword detected: {kw}.")

    # Forbidden dangerous functions (case-insensitive).
    lower = stripped.lower()
    for fn in FORBIDDEN_FUNCTIONS:
        if re.search(rf"\b{re.escape(fn)}\b", lower):
            raise SQLValidationError(f"Forbidden function detected: {fn}.")

    # Return the original (comment-preserving) SQL minus any trailing semicolon,
    # so the executed text is the user/LLM's real query.
    cleaned = raw.rstrip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
    return cleaned


def is_read_only(sql: str) -> bool:
    """Boolean convenience wrapper around :func:`validate_read_only`."""
    try:
        validate_read_only(sql)
        return True
    except SQLValidationError:
        return False


if __name__ == "__main__":  # pragma: no cover - tiny manual smoke test
    import sys

    samples = [
        "SELECT count(*) FROM patients",
        "DELETE FROM patients",
        "SELECT 1; DROP TABLE patients",
        "WITH x AS (DELETE FROM patients RETURNING *) SELECT * FROM x",
        "SELECT name FROM patients WHERE name = 'Robert; DROP TABLE students'",
    ]
    for s in samples:
        ok = is_read_only(s)
        print(f"[{'PASS' if ok else 'BLOCK'}] {s}")
    sys.exit(0)
