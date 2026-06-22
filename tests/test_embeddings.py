"""Tests for the offline embedder (app/embeddings.py).

The offline embedder must be deterministic, fixed-dimension and L2-normalized,
and it must place related sentences nearer than unrelated ones — enough for the
tiny demo corpus to retrieve sensibly with no model download.
"""

import math

from app.embeddings import OfflineEmbedder, get_embedder


def _cosine(a, b):
    return sum(x * y for x, y in zip(a, b))


def test_offline_is_deterministic_and_fixed_dim():
    emb = OfflineEmbedder(dim=128)
    v1 = emb.embed(["how many patients"])[0]
    v2 = emb.embed(["how many patients"])[0]
    assert v1 == v2
    assert len(v1) == 128


def test_offline_vectors_are_normalized():
    emb = OfflineEmbedder()
    [v] = emb.embed(["some clinical text about visits"])
    assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-6)


def test_related_text_is_closer_than_unrelated():
    emb = OfflineEmbedder()
    query, related, unrelated = emb.embed(
        [
            "how many patients are registered",
            "count of patients in the clinic",
            "the weather is sunny today",
        ]
    )
    assert _cosine(query, related) > _cosine(query, unrelated)


def test_get_embedder_factory():
    assert isinstance(get_embedder("offline"), OfflineEmbedder)
    assert isinstance(get_embedder("mock"), OfflineEmbedder)
