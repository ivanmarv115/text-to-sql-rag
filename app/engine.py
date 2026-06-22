"""Text2SQLEngine: RAG retrieval over ChromaDB + read-only SQL execution.

Heavy dependencies (chromadb, psycopg2) are imported lazily so the rest of the
package — and the test-suite — can import the pure modules without them.

Two responsibilities:

* **Retrieval** — embed the question, gather candidate tables from four sources
  (semantic / example / relationship / keyword), merge them by priority
  (:func:`app.retrieval.merge_candidates`) and assemble the LLM context.
* **Execution** — validate the SQL (a second, independent pass — defense in
  depth) and run it on a fresh, read-only PostgreSQL connection with a row cap
  and a statement timeout.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .config import Settings, get_settings
from .embeddings import get_embedder
from . import retrieval, seed_training, validator

logger = logging.getLogger(__name__)

__all__ = ["RetrievedContext", "QueryResult", "Text2SQLEngine"]


@dataclass
class RetrievedContext:
    ddl_blocks: list[str] = field(default_factory=list)
    docs: list[str] = field(default_factory=list)
    examples: list[dict] = field(default_factory=list)  # {question, sql}
    tables: list[str] = field(default_factory=list)

    def as_prompt(self) -> str:
        parts: list[str] = []
        if self.ddl_blocks:
            parts.append("### Tables (DDL)\n" + "\n\n".join(self.ddl_blocks))
        if self.docs:
            parts.append("### Notes\n" + "\n".join(f"- {d}" for d in self.docs))
        if self.examples:
            ex = "\n\n".join(
                f"Q: {e['question']}\nSQL: {e['sql']}" for e in self.examples
            )
            parts.append("### Example queries\n" + ex)
        return "\n\n".join(parts) if parts else "(no schema context retrieved)"


@dataclass
class QueryResult:
    sql: str
    rows: list[dict]
    columns: list[str]
    truncated: bool = False
    row_count: int = 0


class Text2SQLEngine:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.embedder = get_embedder(
            self.settings.embedding_provider,
        )
        self._client = None
        self._collections: dict[str, object] = {}
        # table -> full DDL text, used for relationship following (P3) & payloads
        self._ddl_by_table: dict[str, str] = {
            table.lower(): ddl for table, ddl in _seed_ddl()
        }

    # -- ChromaDB ----------------------------------------------------------

    def _chroma(self):
        if self._client is None:
            import chromadb

            self._client = chromadb.PersistentClient(path=self.settings.chroma_path)
        return self._client

    def _collection(self, name: str):
        if name not in self._collections:
            self._collections[name] = self._chroma().get_or_create_collection(
                name=name, metadata={"hnsw:space": "cosine"}
            )
        return self._collections[name]

    def sync_seed(self) -> str:
        """Idempotently load seed data into the vector store.

        Unchanged items (same content -> same id) are skipped; removed items are
        pruned. Returns a short human-readable summary for the startup log.
        """
        grouped = seed_training.collect_all()
        added_total = 0
        for name, items in grouped.items():
            collection = self._collection(name)
            existing = set(collection.get().get("ids", []))
            wanted = {item.id for item in items}

            stale = list(existing - wanted)
            if stale:
                collection.delete(ids=stale)

            new_items = [item for item in items if item.id not in existing]
            if new_items:
                docs = [it.document for it in new_items]
                collection.add(
                    ids=[it.id for it in new_items],
                    embeddings=self.embedder.embed(docs),
                    documents=docs,
                    metadatas=[it.metadata for it in new_items],
                )
                added_total += len(new_items)
        return f"STARTUP SYNC: complete ({seed_training.summary()}; {added_total} new)"

    # -- retrieval ---------------------------------------------------------

    def _query(self, name: str, embedding: list[float], n: int) -> list[dict]:
        collection = self._collection(name)
        res = collection.query(
            query_embeddings=[embedding],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )
        hits: list[dict] = []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for i in range(len(ids)):
            hits.append(
                {
                    "document": docs[i],
                    "metadata": metas[i] or {},
                    "similarity": 1.0 - float(dists[i]),
                }
            )
        return hits

    def retrieve_context(self, question: str) -> RetrievedContext:
        s = self.settings
        embedding = self.embedder.embed([question])[0]

        # P1 — semantic search across the three collections.
        ddl_hits = self._query(seed_training.DDL_COLLECTION, embedding, s.max_context_items)
        doc_hits = self._query(seed_training.DOC_COLLECTION, embedding, s.max_context_items)
        qsql_hits = self._query(seed_training.QSQL_COLLECTION, embedding, s.max_context_items)

        candidates: list[retrieval.Candidate] = []
        for hit in ddl_hits:
            table = (hit["metadata"].get("table") or "").lower()
            if table:
                candidates.append(
                    retrieval.Candidate(
                        table=table,
                        source="semantic",
                        score=hit["similarity"],
                        payload=hit["document"],
                    )
                )

        # P2 — tables referenced by retrieved example SQL.
        examples: list[dict] = []
        for hit in qsql_hits:
            meta = hit["metadata"]
            sql = meta.get("sql", "")
            examples.append({"question": meta.get("question", hit["document"]), "sql": sql})
            for table in retrieval.extract_tables_from_sql(sql):
                if table in self._ddl_by_table:
                    candidates.append(
                        retrieval.Candidate(
                            table=table,
                            source="example",
                            score=hit["similarity"],
                            payload=self._ddl_by_table[table],
                        )
                    )

        # P3 — follow `-- Joins:` relationships of the tables chosen so far.
        seed_tables = {c.table for c in candidates}
        for table in list(seed_tables):
            for related in retrieval.extract_join_tables(self._ddl_by_table.get(table, "")):
                if related in self._ddl_by_table:
                    candidates.append(
                        retrieval.Candidate(
                            table=related,
                            source="relationship",
                            payload=self._ddl_by_table[related],
                        )
                    )

        # P4 — keyword/substring matches against table names and DDL text.
        for keyword in retrieval.extract_keywords(question):
            for table, ddl in self._ddl_by_table.items():
                if keyword in table or keyword in ddl.lower():
                    candidates.append(
                        retrieval.Candidate(
                            table=table, source="keyword", payload=ddl
                        )
                    )

        merged = retrieval.merge_candidates(candidates, limit=s.max_full_ddl)

        return RetrievedContext(
            ddl_blocks=[c.payload for c in merged],
            docs=[hit["document"] for hit in doc_hits[: s.max_context_items]],
            examples=examples[: s.max_context_items],
            tables=[c.table for c in merged],
        )

    # -- execution ---------------------------------------------------------

    def execute_sql(self, sql: str) -> QueryResult:
        """Validate (defense-in-depth pass #2) and run a read-only query."""
        clean_sql = validator.validate_read_only(sql)  # raises on anything unsafe

        import psycopg2
        from psycopg2.extras import RealDictCursor

        conn = psycopg2.connect(
            self.settings.clinic_dsn,
            # belt-and-braces even though the role is read-only at the DB level
            options="-c default_transaction_read_only=on -c statement_timeout=15000",
        )
        try:
            conn.set_session(readonly=True, autocommit=True)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(clean_sql)
                fetched = cur.fetchmany(self.settings.max_result_rows + 1)
                columns = [desc[0] for desc in cur.description] if cur.description else []
        finally:
            conn.close()

        truncated = len(fetched) > self.settings.max_result_rows
        rows = [dict(r) for r in fetched[: self.settings.max_result_rows]]
        return QueryResult(
            sql=clean_sql,
            rows=rows,
            columns=columns,
            truncated=truncated,
            row_count=len(rows),
        )


def _seed_ddl() -> list[tuple[str, str]]:
    from . import seed_clinic

    return seed_clinic.DDL
