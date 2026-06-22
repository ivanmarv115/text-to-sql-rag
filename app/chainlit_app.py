"""Chainlit application: chat UI, auth, dual-brain routing and the Text-to-SQL
pipeline, plus standard conversation persistence (audit logging).

Run with: ``chainlit run app/chainlit_app.py``.
"""

from __future__ import annotations

import logging
import os

import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer

# Absolute imports: Chainlit loads this file by path, so it must not rely on
# being imported as part of the ``app`` package. PYTHONPATH includes the repo
# root (see Dockerfile), so ``import app`` always resolves.
from app import chainlit_db, nodes
from app.config import get_settings
from app.engine import Text2SQLEngine
from app.llm import LLMClient
from app.mock_responses import SAMPLE_QUESTIONS

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

# --- one-time process initialisation --------------------------------------

_engine: Text2SQLEngine | None = None
_llm: LLMClient | None = None


def _init() -> None:
    """Build the engine/LLM once, sync the seed corpus, ensure the demo login."""
    global _engine, _llm
    if _engine is not None:
        return

    _llm = LLMClient(settings)
    _engine = Text2SQLEngine(settings)

    if settings.seed_on_startup:
        try:
            logger.info(_engine.sync_seed())
        except Exception:  # pragma: no cover - non-fatal; general chat still works
            logger.exception("Seed sync failed; retrieval may be empty")

    if os.environ.get("CREATE_DEMO_USER", "true").lower() in ("1", "true", "yes"):
        chainlit_db.ensure_demo_user(
            os.environ.get("DEMO_USERNAME", "demo"),
            os.environ.get("DEMO_PASSWORD", "demo"),
            display_name="Demo Reviewer",
            role="user",
        )


# Initialise at import so the demo user exists before the login screen.
try:
    _init()
except Exception:  # pragma: no cover
    logger.exception("Initialisation error")


def _engine_llm() -> tuple[Text2SQLEngine, LLMClient]:
    if _engine is None or _llm is None:
        _init()
    assert _engine is not None and _llm is not None
    return _engine, _llm


def _username() -> str:
    user = cl.user_session.get("user")
    return getattr(user, "identifier", "anonymous") if user else "anonymous"


# --- Chainlit hooks ---------------------------------------------------------


@cl.data_layer
def get_data_layer():
    """Standard SQLAlchemy persistence: threads, steps and feedback are written
    to the audit database as the conversation happens."""
    return SQLAlchemyDataLayer(conninfo=settings.chainlit_db_url)


@cl.password_auth_callback
def auth_callback(username: str, password: str):
    user = chainlit_db.verify_user(username, password)
    if not user:
        return None
    return cl.User(
        identifier=user["identifier"],
        metadata={"role": user["role"], "display_name": user["display_name"]},
    )


@cl.set_starters
async def starters():
    return [
        cl.Starter(label=q[:42], message=q) for q in SAMPLE_QUESTIONS[:4]
    ]


@cl.on_chat_start
async def on_chat_start():
    mode = "mock (no model server / GPU needed)" if settings.is_mock else "vLLM"
    await cl.Message(
        content=(
            f"👋 Natural-language-to-SQL assistant — running in **{mode}** mode.\n\n"
            "Ask about the sample clinic database (patients, visits, diagnoses). "
            "I retrieve the relevant schema, generate a **read-only** SQL query, "
            "validate it, run it, and summarise the result."
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    engine, llm = _engine_llm()
    username = _username()
    text = message.content

    # --- conversational feedback on the previous answer ---
    pending = cl.user_session.get("pending_feedback")
    if pending:
        label = llm.classify_feedback(text)
        cl.user_session.set("pending_feedback", None)
        if label.startswith("confirm"):
            chainlit_db.save_sql_feedback(username, pending["question"], pending["sql"], "positive")
            await cl.Message(content="👍 Recorded as positive feedback.").send()
            if label == "confirm":
                return
        elif label.startswith("deny"):
            chainlit_db.save_sql_feedback(username, pending["question"], pending["sql"], "negative")
            await cl.Message(content="👎 Recorded as negative feedback. I'll do better.").send()
            if label == "deny":
                return
        # confirm_and_continue / deny_and_continue / new_query -> fall through

    result = await cl.make_async(nodes.run_text2sql)(text, engine, llm)

    # Optional transparency steps (off by default; DEBUG_CHAT=true to enable).
    if settings.debug_chat and result.sql:
        async with cl.Step(name="Text-to-SQL trace") as step:
            step.output = (
                f"**Routing:** Big Brain · SQL Reasoning\n"
                f"**Tables:** {result.debug.get('tables')}\n"
                f"**Context:** {result.debug.get('context_counts')}\n\n"
                f"```sql\n{result.sql}\n```"
            )

    label = (
        "Big Brain · SQL Reasoning"
        if result.intent == nodes.Intent.DB_QUERY
        else "Small Brain · General"
    )
    await cl.Message(content=result.answer, author=label).send()

    # Ask for feedback on successful DB answers (drives the feedback loop).
    if result.intent == nodes.Intent.DB_QUERY and result.sql and not result.error:
        cl.user_session.set(
            "pending_feedback", {"question": text, "sql": result.sql}
        )
        await cl.Message(content="Was this answer correct? (yes / no)").send()
