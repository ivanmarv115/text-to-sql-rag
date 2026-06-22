"""Seed orchestration.

"Training" here means **loading curated context into ChromaDB for retrieval** —
no model weights are updated and nothing is fine-tuned. This module turns the
raw seed data in :mod:`app.seed_clinic` into stable, idempotent records that the
engine can upsert into the three vector collections (``ddl``, ``documentation``,
``question_sql``).

Each record carries a deterministic ``id`` derived from its content, so syncing
is idempotent: unchanged content keeps the same id and is skipped, changed
content gets a new digest and is re-embedded.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from . import seed_clinic

__all__ = ["SeedItem", "collect_all", "DDL_COLLECTION", "DOC_COLLECTION", "QSQL_COLLECTION"]

DDL_COLLECTION = "ddl"
DOC_COLLECTION = "documentation"
QSQL_COLLECTION = "question_sql"


@dataclass(frozen=True)
class SeedItem:
    collection: str
    id: str
    document: str  # the text that gets embedded
    metadata: dict = field(default_factory=dict)


def _digest(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


def collect_all() -> dict[str, list[SeedItem]]:
    """Return seed items grouped by collection name."""
    ddl_items = [
        SeedItem(
            collection=DDL_COLLECTION,
            id=f"ddl::{table}::{_digest(ddl)}",
            document=ddl,
            metadata={"table": table},
        )
        for table, ddl in seed_clinic.DDL
    ]

    doc_items = [
        SeedItem(
            collection=DOC_COLLECTION,
            id=f"doc::{topic}::{_digest(text)}",
            document=text,
            metadata={"topic": topic},
        )
        for topic, text in seed_clinic.DOCS
    ]

    # For Q&A pairs the *question* is embedded; the SQL rides along in metadata.
    qsql_items = [
        SeedItem(
            collection=QSQL_COLLECTION,
            id=f"qsql::{_digest(question, sql)}",
            document=question,
            metadata={"question": question, "sql": sql},
        )
        for question, sql in seed_clinic.EXAMPLES
    ]

    return {
        DDL_COLLECTION: ddl_items,
        DOC_COLLECTION: doc_items,
        QSQL_COLLECTION: qsql_items,
    }


def summary() -> str:
    counts = {name: len(items) for name, items in collect_all().items()}
    return (
        f"{counts[DDL_COLLECTION]} DDLs, "
        f"{counts[DOC_COLLECTION]} docs, "
        f"{counts[QSQL_COLLECTION]} examples"
    )
