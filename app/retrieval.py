"""RAG context-retrieval logic (priority merge), kept pure and dependency-free.

The :class:`~app.engine.Text2SQLEngine` is responsible for the I/O — querying
ChromaDB, reading seed data — but the *decision* logic for how candidate tables
are ranked and merged lives here so it can be unit-tested without a vector
store.

Context is gathered from four sources, in descending priority:

* **P1 semantic**     – nearest neighbours from ChromaDB (cosine similarity).
* **P2 example**      – tables referenced by the SQL of retrieved Q&A pairs.
* **P3 relationship** – tables named in ``-- Joins:`` annotations on DDL we
  already decided to include.
* **P4 keyword**      – substring/keyword matches on the question.

When the same table is surfaced by several sources, the highest-priority source
wins. Within a priority tier, higher semantic similarity wins.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "PRIORITY",
    "Candidate",
    "merge_candidates",
    "extract_tables_from_sql",
    "extract_join_tables",
    "extract_keywords",
]

# Lower number == higher priority.
PRIORITY: dict[str, int] = {
    "semantic": 1,
    "example": 2,
    "relationship": 3,
    "keyword": 4,
}


@dataclass
class Candidate:
    """A single candidate table to include in the LLM context."""

    table: str
    source: str  # one of PRIORITY's keys
    score: float = 0.0  # similarity in [0, 1]; higher is better
    payload: str = ""  # the DDL / document text to send to the model

    def __post_init__(self) -> None:
        self.table = self.table.strip().lower()
        if self.source not in PRIORITY:
            raise ValueError(f"Unknown retrieval source: {self.source!r}")

    @property
    def rank(self) -> tuple[int, float]:
        # Sort key: priority ascending, then similarity descending.
        return (PRIORITY[self.source], -self.score)


def merge_candidates(candidates: list[Candidate], limit: int) -> list[Candidate]:
    """De-duplicate by table (best source wins) and return the top ``limit``.

    Ordering is deterministic: by priority, then by descending similarity, then
    by table name (so equal-ranked results are stable).
    """
    if limit < 0:
        raise ValueError("limit must be >= 0")

    best: dict[str, Candidate] = {}
    for cand in candidates:
        current = best.get(cand.table)
        if current is None or cand.rank < current.rank:
            best[cand.table] = cand

    ordered = sorted(best.values(), key=lambda c: (c.rank[0], c.rank[1], c.table))
    return ordered[:limit]


# --- helpers ---------------------------------------------------------------

# Matches the table reference that follows FROM / JOIN. Captures an optional
# schema-qualified, optionally double-quoted identifier.
_TABLE_RE = re.compile(
    r'\b(?:FROM|JOIN)\s+("?[A-Za-z_][\w$]*"?(?:\.\s*"?[A-Za-z_][\w$]*"?)?)',
    re.IGNORECASE,
)

_JOIN_ANNOTATION_RE = re.compile(r"--\s*Joins?\s*:\s*(.+)", re.IGNORECASE)


def _normalize_table(token: str) -> str:
    token = token.strip().strip('"').lower()
    # keep only the table part of schema.table
    if "." in token:
        token = token.split(".")[-1].strip().strip('"')
    return token


def extract_tables_from_sql(sql: str) -> set[str]:
    """Return the set of (lower-cased, unqualified) table names a query reads."""
    if not sql:
        return set()
    tables: set[str] = set()
    for match in _TABLE_RE.finditer(sql):
        name = _normalize_table(match.group(1))
        if name:
            tables.add(name)
    return tables


def extract_join_tables(ddl_text: str) -> list[str]:
    """Parse ``-- Joins: a, b`` annotations from a DDL block.

    Returns table names in declaration order, de-duplicated, lower-cased.
    """
    if not ddl_text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for line in ddl_text.splitlines():
        m = _JOIN_ANNOTATION_RE.search(line)
        if not m:
            continue
        for raw in re.split(r"[,;]", m.group(1)):
            name = _normalize_table(raw)
            if name and name not in seen:
                seen.add(name)
                found.append(name)
    return found


_STOPWORDS = {
    # English
    "the", "a", "an", "how", "many", "much", "is", "are", "of", "in", "on",
    "for", "to", "and", "or", "what", "which", "who", "when", "list", "show",
    "me", "all", "count", "number", "give", "there", "this", "that", "by",
    # Spanish (the embedding model is multilingual; queries may be in either)
    "cuantos", "cuantas", "cuanto", "cuanta", "los", "las", "el", "la", "de",
    "del", "en", "por", "para", "que", "cual", "cuales", "hay", "con", "una",
    "uno", "dame", "muestrame", "lista", "numero",
}


def extract_keywords(question: str) -> list[str]:
    """Lower-cased content words from a question, stop-words removed."""
    tokens = re.findall(r"[A-Za-zÀ-ÿ][\wÀ-ÿ]+", question.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 2]
