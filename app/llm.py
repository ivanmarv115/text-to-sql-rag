"""LLM clients with a dual-brain router and an offline mock mode.

Two "brains" mirror the real deployment:

* **Big Brain**   – a large dense instruct model served with vLLM; used for the
  hard task (SQL generation) and question rewriting.
* **Small Brain** – a small, quantized instruct model served with vLLM; used for
  cheap/fast tasks (response formatting, feedback parsing, general chat).

Both are reached over the OpenAI-compatible API that vLLM exposes. When
``LLM_MODE=mock`` no server is contacted at all: SQL comes from
``app.mock_responses`` and chat replies are canned. This is what lets the demo
run on a laptop with no GPU.
"""

from __future__ import annotations

import logging
from enum import Enum

from .config import BrainConfig, Settings, get_settings
from . import mock_responses

logger = logging.getLogger(__name__)

__all__ = ["Brain", "LLMClient"]


class Brain(str, Enum):
    BIG = "big"
    SMALL = "small"


class LLMClient:
    """Thin wrapper over the two vLLM endpoints, with a mock short-circuit."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._clients: dict[Brain, object] = {}

    # -- public API ---------------------------------------------------------

    @property
    def is_mock(self) -> bool:
        return self.settings.is_mock

    def generate_sql(self, question: str, context: str) -> str | None:
        """Return SQL for ``question``. ``None`` if the model declined."""
        if self.is_mock:
            match = mock_responses.match_sql(question)
            return match.sql if match else None

        from .prompts import SQL_SYSTEM_PROMPT

        text = self._chat(
            Brain.BIG,
            system=SQL_SYSTEM_PROMPT.format(context=context),
            user=question,
        )
        return _extract_sql(text)

    def rewrite_question(self, question: str, history: str) -> str:
        if self.is_mock:
            return question
        from .prompts import REWRITE_SYSTEM_PROMPT

        return self._chat(
            Brain.BIG,
            system=REWRITE_SYSTEM_PROMPT,
            user=f"Conversation so far:\n{history}\n\nLatest message: {question}",
        ).strip() or question

    def format_answer(self, question: str, rows: list[dict]) -> str:
        if self.is_mock:
            return _format_rows_markdown(question, rows)
        from .prompts import FORMAT_SYSTEM_PROMPT

        return self._chat(
            Brain.SMALL,
            system=FORMAT_SYSTEM_PROMPT,
            user=f"Question: {question}\n\nResult rows (JSON): {rows}",
        )

    def classify_feedback(self, reply: str) -> str:
        if self.is_mock:
            return _keyword_feedback(reply)
        from .prompts import FEEDBACK_SYSTEM_PROMPT

        label = self._chat(
            Brain.SMALL, system=FEEDBACK_SYSTEM_PROMPT, user=reply
        ).strip().lower()
        valid = {"confirm", "deny", "confirm_and_continue", "deny_and_continue", "new_query"}
        return label if label in valid else "new_query"

    def general_reply(self, question: str) -> str:
        if self.is_mock:
            return mock_responses.canned_chat(question)
        from .prompts import GENERAL_SYSTEM_PROMPT

        return self._chat(Brain.SMALL, system=GENERAL_SYSTEM_PROMPT, user=question)

    # -- vLLM plumbing ------------------------------------------------------

    def _brain_config(self, brain: Brain) -> BrainConfig:
        return self.settings.big_brain if brain is Brain.BIG else self.settings.small_brain

    def _client(self, brain: Brain):
        if brain not in self._clients:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "LLM_MODE=vllm requires the 'openai' package (it is in "
                    "requirements.txt)."
                ) from exc
            cfg = self._brain_config(brain)
            self._clients[brain] = OpenAI(
                base_url=cfg.base_url, api_key=cfg.api_key or "not-needed"
            )
        return self._clients[brain]

    def _chat(self, brain: Brain, *, system: str, user: str) -> str:  # pragma: no cover
        cfg = self._brain_config(brain)
        client = self._client(brain)
        resp = client.chat.completions.create(
            model=cfg.model,
            temperature=cfg.temperature,
            top_p=cfg.top_p,
            extra_body={"top_k": cfg.top_k},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""


# --- helpers (also useful in mock mode) ------------------------------------


def _extract_sql(text: str | None) -> str | None:
    """Pull a SQL statement out of a model response (```sql block or raw)."""
    if not text:
        return None
    import re

    fenced = re.search(r"```(?:sql)?\s*(.+?)```", text, re.IGNORECASE | re.DOTALL)
    candidate = (fenced.group(1) if fenced else text).strip()
    return candidate or None


def _keyword_feedback(reply: str) -> str:
    text = (reply or "").strip().lower()
    positive = any(w in text for w in ("yes", "correct", "right", "sí", "si", "correcto"))
    negative = any(w in text for w in ("no", "wrong", "incorrect", "incorrecto", "mal"))
    has_follow_up = "?" in text or len(text.split()) > 4
    if positive and has_follow_up:
        return "confirm_and_continue"
    if negative and has_follow_up:
        return "deny_and_continue"
    if positive:
        return "confirm"
    if negative:
        return "deny"
    return "new_query"


def _format_rows_markdown(question: str, rows: list[dict]) -> str:
    """Plain, deterministic result formatting used in mock mode."""
    if not rows:
        return "The query returned no rows."
    if len(rows) == 1 and len(rows[0]) == 1:
        (key, value), = rows[0].items()
        return f"**{key.replace('_', ' ').title()}:** {value}"

    headers = list(rows[0].keys())
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
    return "\n".join(lines)
