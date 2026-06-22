"""Synchronous helpers for the Chainlit / audit-log database.

This database stores authentication credentials, conversation history (via
Chainlit's data layer) and query feedback. Conversation persistence here is
standard application audit logging: threads and messages are written as they
happen so the system's activity can be reviewed and good question->SQL pairs can
be promoted into the seed set.

Kept separate from the asyncpg-based Chainlit data layer because auth and
feedback writes are simple synchronous operations.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

__all__ = ["sync_dsn", "verify_user", "save_sql_feedback", "ensure_demo_user"]


def sync_dsn() -> str:
    """libpq DSN for the Chainlit/audit database (psycopg2, synchronous)."""
    return (
        "host={host} port={port} dbname={db} user={user} password={pw}".format(
            host=os.environ.get("CHAINLIT_DB_HOST", "db"),
            port=os.environ.get("CHAINLIT_DB_PORT", "5432"),
            db=os.environ.get("CHAINLIT_DB_NAME", "chainlit"),
            user=os.environ.get("CHAINLIT_DB_USER", "app"),
            pw=os.environ.get("CHAINLIT_DB_PASSWORD", ""),
        )
    )


def verify_user(username: str, password: str) -> dict | None:
    """Return user info dict if credentials are valid, else ``None``."""
    import bcrypt
    import psycopg2

    try:
        conn = psycopg2.connect(sync_dsn())
    except Exception:  # pragma: no cover - DB may be unavailable
        logger.exception("Could not connect to the auth database")
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT hashed_password, display_name, role "
                "FROM user_credentials WHERE identifier = %s",
                (username,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return None
    hashed_password, display_name, role = row
    if not bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8")):
        return None
    return {"identifier": username, "display_name": display_name, "role": role or "user"}


def ensure_demo_user(
    username: str,
    password: str,
    display_name: str = "Demo User",
    role: str = "user",
    *,
    retries: int = 30,
    delay: float = 2.0,
) -> bool:
    """Idempotently create/refresh a demo login so the app is usable on first run.

    The bcrypt hash is computed here (inside the container, where bcrypt is
    installed) rather than baked into a migration, so the password stays in one
    documented place. Retries while the database / Flyway migrations come up.
    Returns ``True`` if the user is present afterwards.
    """
    import time

    import bcrypt
    import psycopg2

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            conn = psycopg2.connect(sync_dsn())
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO user_credentials
                            (identifier, hashed_password, display_name, role)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (identifier) DO UPDATE
                            SET hashed_password = EXCLUDED.hashed_password,
                                display_name   = EXCLUDED.display_name,
                                role           = EXCLUDED.role
                        """,
                        (username, hashed, display_name, role),
                    )
                conn.commit()
            finally:
                conn.close()
            logger.info("Demo user '%s' is ready.", username)
            return True
        except Exception as exc:  # table/DB not ready yet -> retry
            last_err = exc
            time.sleep(delay)
    logger.warning("Could not ensure demo user after %s attempts: %s", retries, last_err)
    return False


def save_sql_feedback(username: str, question: str, sql: str, feedback: str) -> None:
    """Persist a feedback row. Best-effort: never raises into the chat flow."""
    import psycopg2

    try:
        conn = psycopg2.connect(sync_dsn())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO sql_feedback (username, question, sql, feedback) "
                    "VALUES (%s, %s, %s, %s)",
                    (username, question, sql, feedback),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:  # pragma: no cover - feedback is non-critical
        logger.exception("Could not save SQL feedback")
