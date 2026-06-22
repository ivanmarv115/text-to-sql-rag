"""Pluggable text-embedding providers.

Two providers are supported:

* ``offline`` – a deterministic, fully local hashing embedder. No network, no
  model download, no GPU. Quality is modest but it is perfectly adequate for the
  tiny demo corpus and lets ``docker compose up`` work out of the box. This is
  the default in mock mode.
* ``bge-m3`` – ``BAAI/bge-m3`` via ``sentence-transformers``: a 1024-dim
  multilingual model that matches natural-language questions (English, Spanish,
  …) against SQL/DDL. This is the provider used in the real, GPU-backed setup.
  It is imported lazily so the offline path never needs ``torch`` installed.

The engine asks a provider to ``embed(texts)`` and passes the resulting vectors
straight to ChromaDB (``embeddings=`` / ``query_embeddings=``), so we never rely
on ChromaDB's own embedding-function plumbing.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

__all__ = ["Embedder", "OfflineEmbedder", "BGEM3Embedder", "get_embedder"]


class Embedder(Protocol):
    dim: int
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9_]+")


class OfflineEmbedder:
    """Deterministic local embedder: hashed bag-of-words + char trigrams.

    Produces L2-normalized vectors so dot-product == cosine similarity. It has
    no external dependencies and is stable across runs/machines, which also
    makes it convenient to unit-test.
    """

    name = "offline-hash"

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _features(self, text: str) -> list[str]:
        text = text.lower()
        tokens = _TOKEN_RE.findall(text)
        feats = list(tokens)
        # character trigrams add a little fuzziness / morphological robustness
        for tok in tokens:
            padded = f"#{tok}#"
            for i in range(len(padded) - 2):
                feats.append(padded[i : i + 3])
        return feats

    def _bucket(self, feature: str) -> int:
        digest = hashlib.md5(feature.encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "big") % self.dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for feat in self._features(text or ""):
                vec[self._bucket(feat)] += 1.0
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            vectors.append(vec)
        return vectors


class BGEM3Embedder:
    """``BAAI/bge-m3`` multilingual embedder (lazy ``sentence-transformers``)."""

    name = "bge-m3"
    dim = 1024

    def __init__(self, model_name: str = "BAAI/bge-m3") -> None:
        self.model_name = model_name
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - depends on extras
                raise RuntimeError(
                    "EMBEDDING_PROVIDER=bge-m3 requires the embeddings extra. "
                    "Install it with: pip install -r requirements-embeddings.txt"
                ) from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover
        model = self._ensure_model()
        return model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True
        ).tolist()


def get_embedder(provider: str, *, dim: int = 256) -> Embedder:
    """Return an embedder for ``provider`` ('offline' | 'bge-m3')."""
    provider = (provider or "offline").lower()
    if provider in ("offline", "hash", "mock", "local"):
        return OfflineEmbedder(dim=dim)
    if provider in ("bge-m3", "bge", "bgem3"):
        return BGEM3Embedder()
    raise ValueError(f"Unknown embedding provider: {provider!r}")
