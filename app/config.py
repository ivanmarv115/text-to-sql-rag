"""Environment-driven configuration.

Everything is configured through environment variables (see ``.env.example``).
Importing this module never requires a database or a model server, and the
optional ``python-dotenv`` dependency is loaded best-effort so this is safe to
import from tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

try:  # load a local .env if python-dotenv is installed; harmless otherwise
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _bool(name: str, default: bool = False) -> bool:
    return _env(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class BrainConfig:
    base_url: str
    model: str
    api_key: str
    temperature: float
    top_p: float
    top_k: int


@dataclass(frozen=True)
class Settings:
    # --- LLM mode -----------------------------------------------------------
    # "mock"  -> canned SQL, no model server, no GPU (default; demo-friendly)
    # "vllm"  -> talk to OpenAI-compatible vLLM servers (real deployment)
    llm_mode: str = "mock"

    # --- read-only target (clinic) database --------------------------------
    pg_host: str = "db"
    pg_port: int = 5432
    pg_dbname: str = "clinic_demo"
    pg_user: str = "llm_readonly"
    pg_password: str = ""

    # --- Chainlit / audit-log database -------------------------------------
    chainlit_db_url: str = ""

    # --- retrieval ----------------------------------------------------------
    embedding_provider: str = "offline"
    chroma_path: str = "/data/chroma"
    max_context_items: int = 8
    max_full_ddl: int = 6
    max_summary_ddl: int = 12
    max_result_rows: int = 1000
    max_history_turns: int = 10
    seed_on_startup: bool = True

    # --- dual-brain vLLM ----------------------------------------------------
    big_brain: BrainConfig = field(
        default_factory=lambda: BrainConfig(
            base_url=_env("VLLM_BIG_BRAIN_BASE_URL", "http://localhost:8000/v1"),
            model=_env("VLLM_BIG_BRAIN_MODEL", "big-instruct-model"),
            api_key=_env("VLLM_BIG_BRAIN_API_KEY", ""),
            temperature=float(_env("VLLM_BIG_BRAIN_TEMPERATURE", "0.1")),
            top_p=float(_env("VLLM_BIG_BRAIN_TOP_P", "0.95")),
            top_k=_int("VLLM_BIG_BRAIN_TOP_K", 64),
        )
    )
    small_brain: BrainConfig = field(
        default_factory=lambda: BrainConfig(
            base_url=_env("VLLM_SMALL_BRAIN_BASE_URL", "http://localhost:8001/v1"),
            model=_env("VLLM_SMALL_BRAIN_MODEL", "small-instruct-model"),
            api_key=_env("VLLM_SMALL_BRAIN_API_KEY", ""),
            temperature=float(_env("VLLM_SMALL_BRAIN_TEMPERATURE", "1.0")),
            top_p=float(_env("VLLM_SMALL_BRAIN_TOP_P", "0.95")),
            top_k=_int("VLLM_SMALL_BRAIN_TOP_K", 64),
        )
    )

    # --- misc ---------------------------------------------------------------
    debug_chat: bool = False
    log_level: str = "INFO"

    @property
    def is_mock(self) -> bool:
        return self.llm_mode.strip().lower() == "mock"

    @property
    def clinic_dsn(self) -> str:
        """libpq DSN for the read-only clinic database."""
        return (
            f"host={self.pg_host} port={self.pg_port} dbname={self.pg_dbname} "
            f"user={self.pg_user} password={self.pg_password}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    llm_mode = _env("LLM_MODE", "mock").strip().lower()

    # In mock mode default to the offline embedder so no model is downloaded;
    # in vLLM mode default to bge-m3. Either can be overridden explicitly. An
    # empty value (e.g. an unset compose variable) falls back to the default.
    default_embed = "offline" if llm_mode == "mock" else "bge-m3"
    embedding_provider = _env("EMBEDDING_PROVIDER", "").strip() or default_embed

    chainlit_db_url = _env(
        "CHAINLIT_DB_URL",
        "postgresql+asyncpg://{u}:{p}@{h}:{port}/{db}".format(
            u=_env("CHAINLIT_DB_USER", "app"),
            p=_env("CHAINLIT_DB_PASSWORD", ""),
            h=_env("CHAINLIT_DB_HOST", "db"),
            port=_env("CHAINLIT_DB_PORT", "5432"),
            db=_env("CHAINLIT_DB_NAME", "chainlit"),
        ),
    )

    return Settings(
        llm_mode=llm_mode,
        pg_host=_env("PG_HOST", "db"),
        pg_port=_int("PG_PORT", 5432),
        pg_dbname=_env("PG_DBNAME", "clinic_demo"),
        pg_user=_env("PG_USER", "llm_readonly"),
        pg_password=_env("PG_PASSWORD", ""),
        chainlit_db_url=chainlit_db_url,
        embedding_provider=embedding_provider,
        chroma_path=_env("CHROMA_PATH", "/data/chroma"),
        max_context_items=_int("MAX_CONTEXT_ITEMS", 8),
        max_full_ddl=_int("MAX_FULL_DDL", 6),
        max_summary_ddl=_int("MAX_SUMMARY_DDL", 12),
        max_result_rows=_int("MAX_RESULT_ROWS", 1000),
        max_history_turns=_int("MAX_HISTORY_TURNS", 10),
        seed_on_startup=_bool("SEED_ON_STARTUP", True),
        debug_chat=_bool("DEBUG_CHAT", False),
        log_level=_env("LOG_LEVEL", "INFO"),
    )
