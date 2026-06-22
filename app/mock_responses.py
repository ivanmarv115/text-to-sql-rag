"""Canned LLM responses for offline / mock mode (``LLM_MODE=mock``).

In mock mode no model server (and no GPU) is required: a reviewer can run
``docker compose up`` and immediately try the assistant. The "LLM" simply maps a
few recognised sample questions to hand-written SQL. That SQL is still run
through the real validator and executed against the real (synthetic) read-only
database, so the end-to-end pipeline — retrieval, validation, execution,
formatting — is genuinely exercised.

Questions are matched in a language-agnostic way (English and Spanish triggers)
to show off the multilingual nature of the real ``bge-m3`` setup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["CANNED", "SAMPLE_QUESTIONS", "match_sql", "canned_chat"]


@dataclass(frozen=True)
class CannedQuery:
    label: str
    domain: str
    triggers: tuple[str, ...]
    sql: str


# NB: every SQL string below is a single read-only SELECT and passes
# app.validator.validate_read_only. Tables/columns match flyway/clinic.
CANNED: tuple[CannedQuery, ...] = (
    CannedQuery(
        label="Count patients",
        domain="patients",
        triggers=("patient", "paciente", "pacientes"),
        sql="SELECT COUNT(*) AS total_patients FROM patients",
    ),
    CannedQuery(
        label="Count doctors",
        domain="staff",
        triggers=("doctor", "doctors", "medico", "medicos", "médico", "médicos"),
        sql="SELECT COUNT(*) AS total_doctors FROM doctors",
    ),
    CannedQuery(
        label="Visits this month",
        domain="visits",
        triggers=("this month", "este mes", "visitas este mes", "visit month"),
        sql=(
            "SELECT COUNT(*) AS visits_this_month\n"
            "FROM visits\n"
            "WHERE date_trunc('month', visit_date) = date_trunc('month', CURRENT_DATE)"
        ),
    ),
    CannedQuery(
        label="Most common diagnoses",
        domain="diagnoses",
        triggers=(
            "common diagnos",
            "top diagnos",
            "diagnos",
            "diagnostico",
            "diagnósticos comunes",
        ),
        sql=(
            "SELECT code, description, COUNT(*) AS occurrences\n"
            "FROM diagnoses\n"
            "GROUP BY code, description\n"
            "ORDER BY occurrences DESC\n"
            "LIMIT 5"
        ),
    ),
    CannedQuery(
        label="Visits per department",
        domain="visits",
        triggers=(
            "per department",
            "by department",
            "visits department",
            "por departamento",
            "por servicio",
        ),
        sql=(
            "SELECT dep.name AS department, COUNT(*) AS visits\n"
            "FROM visits v\n"
            "JOIN departments dep ON dep.department_id = v.department_id\n"
            "GROUP BY dep.name\n"
            "ORDER BY visits DESC"
        ),
    ),
    CannedQuery(
        label="Patients per city",
        domain="patients",
        triggers=("per city", "by city", "patients city", "por ciudad", "ciudad"),
        sql=(
            "SELECT city, COUNT(*) AS patients\n"
            "FROM patients\n"
            "GROUP BY city\n"
            "ORDER BY patients DESC"
        ),
    ),
)


# Friendly starter questions surfaced in the UI / docs.
SAMPLE_QUESTIONS: tuple[str, ...] = (
    "How many patients are there?",
    "¿Cuántos pacientes hay?",
    "How many visits happened this month?",
    "What are the most common diagnoses?",
    "How many visits per department?",
    "How many patients per city?",
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def match_sql(question: str) -> CannedQuery | None:
    """Return the best-matching canned query for ``question``, or ``None``.

    Each matched trigger contributes its word count to the score, so a specific
    multi-word trigger ("per city") outranks a generic single word ("patient").
    The highest-scoring entry wins; ties resolve to declaration order.
    """
    q = _normalize(question)
    if not q:
        return None
    best: CannedQuery | None = None
    best_score = 0
    for entry in CANNED:
        score = sum(len(t.split()) for t in entry.triggers if t in q)
        if score > best_score:
            best_score = score
            best = entry
    return best if best_score > 0 else None


def canned_chat(question: str) -> str:
    """A canned reply for general (non-database) chat in mock mode."""
    q = _normalize(question)
    if any(greet in q for greet in ("hello", "hi", "hola", "buenas")):
        return (
            "Hi! I'm a demo natural-language-to-SQL assistant running in **mock "
            "mode** (no model server required). Ask me about the sample clinic "
            "data — for example: *“How many patients are there?”* or "
            "*“What are the most common diagnoses?”*"
        )
    return (
        "I'm running in **mock mode**, so I only answer from a small set of "
        "sample questions about the demo clinic database. Try one of: "
        + "; ".join(f"“{s}”" for s in SAMPLE_QUESTIONS[:4])
        + ". Switch to `LLM_MODE=vllm` with a real model server for open-ended "
        "questions."
    )
