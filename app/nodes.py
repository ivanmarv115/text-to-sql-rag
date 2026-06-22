"""Pipeline nodes: the text-to-SQL flow, broken into small testable steps.

Intent classification is pure keyword logic (zero latency, no LLM). The rest of
the flow — rewrite, retrieve, generate, validate, execute, format — is wired
together in :func:`run_text2sql`.

Note the SQL is validated **here** (pipeline layer) *and* again inside
``engine.execute_sql`` (execution layer). Two independent passes = defense in
depth.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from . import validator
from .engine import RetrievedContext, Text2SQLEngine
from .llm import LLMClient

logger = logging.getLogger(__name__)

__all__ = ["Intent", "classify_intent", "PipelineResult", "run_text2sql"]


class Intent:
    DB_QUERY = "db_query"
    GENERAL = "general"


# Words that strongly suggest the user wants data from the database.
_DB_HINTS = (
    "how many", "count", "list", "show", "average", "total", "per ",
    "patient", "visit", "diagnos", "doctor", "department", "city",
    "cuant", "pacient", "visita", "diagnos", "medico", "médico",
    "departamento", "ciudad", "lista", "promedio",
)


def classify_intent(text: str) -> str:
    """Cheap keyword router: database question vs. general chat."""
    t = (text or "").lower()
    if "?" in t and any(h in t for h in _DB_HINTS):
        return Intent.DB_QUERY
    if any(h in t for h in _DB_HINTS):
        return Intent.DB_QUERY
    return Intent.GENERAL


@dataclass
class PipelineResult:
    intent: str
    answer: str
    sql: str | None = None
    rows: list[dict] = field(default_factory=list)
    error: str | None = None
    debug: dict = field(default_factory=dict)


def run_text2sql(
    question: str,
    engine: Text2SQLEngine,
    llm: LLMClient,
    history: str = "",
) -> PipelineResult:
    """Run the full pipeline for one user question."""
    intent = classify_intent(question)
    if intent == Intent.GENERAL:
        return PipelineResult(intent=intent, answer=llm.general_reply(question))

    debug: dict = {}

    rewritten = llm.rewrite_question(question, history) if history else question
    debug["rewritten"] = rewritten

    try:
        context = engine.retrieve_context(rewritten)
    except Exception:  # pragma: no cover - retrieval is best-effort
        logger.exception("Retrieval failed; continuing with empty context")
        context = RetrievedContext()
    debug["tables"] = context.tables
    debug["context_counts"] = {
        "ddl": len(context.ddl_blocks),
        "docs": len(context.docs),
        "examples": len(context.examples),
    }

    sql = llm.generate_sql(rewritten, context.as_prompt())
    if not sql:
        return PipelineResult(
            intent=intent,
            answer=(
                "I couldn't produce a query for that. In mock mode try one of the "
                "sample questions; in vLLM mode rephrase and try again."
            ),
            debug=debug,
        )

    # --- defense-in-depth validation pass #1 (pipeline layer) ---
    try:
        sql = validator.validate_read_only(sql)
    except validator.SQLValidationError as exc:
        logger.warning("Blocked unsafe SQL at pipeline layer: %s", exc)
        return PipelineResult(
            intent=intent,
            answer="The generated query was rejected by the safety validator.",
            sql=sql,
            error=str(exc),
            debug=debug,
        )

    debug["sql"] = sql

    try:
        result = engine.execute_sql(sql)  # validation pass #2 happens inside
    except validator.SQLValidationError as exc:
        return PipelineResult(
            intent=intent,
            answer="The generated query was rejected by the safety validator.",
            sql=sql,
            error=str(exc),
            debug=debug,
        )
    except Exception as exc:  # pragma: no cover - DB/runtime errors
        logger.exception("Query execution failed")
        return PipelineResult(
            intent=intent,
            answer=f"The query could not be executed: {exc}",
            sql=sql,
            error=str(exc),
            debug=debug,
        )

    answer = llm.format_answer(question, result.rows)
    if result.truncated:
        answer += f"\n\n_(showing first {len(result.rows)} rows)_"

    return PipelineResult(
        intent=intent,
        answer=answer,
        sql=sql,
        rows=result.rows,
        debug=debug,
    )
