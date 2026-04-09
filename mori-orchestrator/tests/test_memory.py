"""
Tests for src/memory.py — Memory class with vector support.
"""
from __future__ import annotations

import json
import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory import Memory, OllamaEmbedder, cosine_similarity, tfidf_score


# ── Helpers ───────────────────────────────────────────────────

def _make_config(enabled: bool = True, sources: list[str] | None = None):
    """Build a minimal MoriConfig-like mock."""
    mem_cfg = MagicMock()
    mem_cfg.enabled = enabled
    mem_cfg.embedding_model = "nomic-embed-text"
    mem_cfg.top_k = 5
    mem_cfg.sources = sources or ["notes", "decisions", "task_history"]
    mem_cfg.fallback = "tfidf"

    config = MagicMock()
    config.memory = mem_cfg
    config.models = []  # no ollama models configured → uses default localhost
    return config


def _make_db():
    db = MagicMock()
    db.search_notes_fts = AsyncMock(return_value=[])
    db.search_similar_tasks = AsyncMock(return_value=[])
    db.get_all_embeddings = AsyncMock(return_value=[])
    db.get_unembedded_notes = AsyncMock(return_value=[])
    db.store_embedding = AsyncMock(return_value="chunk-id")
    return db


# ── Test: cosine_similarity ────────────────────────────────────

def test_cosine_similarity_identical_vectors():
    v = [1.0, 0.0, 0.0]
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors():
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(0.0)


def test_cosine_similarity_known_values():
    a = [1.0, 2.0, 3.0]
    b = [4.0, 5.0, 6.0]
    dot = 1 * 4 + 2 * 5 + 3 * 6  # = 32
    mag_a = math.sqrt(1 + 4 + 9)  # sqrt(14)
    mag_b = math.sqrt(16 + 25 + 36)  # sqrt(77)
    expected = dot / (mag_a * mag_b)
    assert cosine_similarity(a, b) == pytest.approx(expected)


def test_cosine_similarity_zero_vector():
    a = [0.0, 0.0, 0.0]
    b = [1.0, 2.0, 3.0]
    assert cosine_similarity(a, b) == 0.0


# ── Test: tfidf_score ─────────────────────────────────────────

def test_tfidf_score_exact_match():
    score = tfidf_score("hello world", "hello world")
    assert score == pytest.approx(1.0)


def test_tfidf_score_no_match():
    score = tfidf_score("hello world", "foo bar baz")
    assert score == pytest.approx(0.0)


def test_tfidf_score_partial_match():
    score = tfidf_score("hello world", "hello foo bar")
    # 1 out of 3 doc terms matches
    assert score == pytest.approx(1 / 3)


def test_tfidf_score_empty_document():
    score = tfidf_score("hello", "")
    assert score == 0.0


# ── Test: _build_query ────────────────────────────────────────

def test_build_query_from_task():
    config = _make_config()
    db = _make_db()
    memory = Memory(config, db)

    task = {
        "title": "Fix login bug",
        "description": "Users can't log in after token expiry",
        "tags": ["auth", "backend"],
    }
    query = memory._build_query(task)
    assert "Fix login bug" in query
    assert "Users can't log in" in query
    assert "auth" in query
    assert "backend" in query


def test_build_query_minimal_task():
    config = _make_config()
    db = _make_db()
    memory = Memory(config, db)

    task = {"title": "Deploy to production"}
    query = memory._build_query(task)
    assert query == "Deploy to production"


def test_build_query_with_json_tags():
    config = _make_config()
    db = _make_db()
    memory = Memory(config, db)

    task = {"title": "Review PR", "tags": '["python", "review"]'}
    query = memory._build_query(task)
    assert "python" in query
    assert "review" in query


def test_build_query_empty_task():
    config = _make_config()
    db = _make_db()
    memory = Memory(config, db)

    query = memory._build_query({})
    assert query == ""


# ── Test: retrieve — disabled memory ─────────────────────────

@pytest.mark.asyncio
async def test_retrieve_returns_empty_when_disabled():
    config = _make_config(enabled=False)
    db = _make_db()
    memory = Memory(config, db)

    result = await memory.retrieve({"title": "Some task"})
    assert result == ""
    db.search_notes_fts.assert_not_called()


# ── Test: FTS fallback when no embeddings ─────────────────────

@pytest.mark.asyncio
async def test_fts_fallback_when_no_embeddings():
    """When Ollama is unavailable, FTS5 is used."""
    config = _make_config()
    db = _make_db()
    db.search_notes_fts = AsyncMock(return_value=[
        {
            "id": "n1",
            "title": "Auth notes",
            "content": "JWT tokens expire after 1h",
            "type": "nota",
            "updated_at": "2024-01-15T10:00:00Z",
        }
    ])
    db.get_all_embeddings = AsyncMock(return_value=[])

    memory = Memory(config, db)
    # Simulate Ollama not available
    memory.embedder._available = False
    memory._embedder_checked = True

    result = await memory.retrieve({"title": "JWT auth problem", "description": ""})
    assert "Auth notes" in result
    assert "JWT tokens expire" in result


@pytest.mark.asyncio
async def test_fts_fallback_includes_task_history():
    """Task history FTS results are included in fallback."""
    config = _make_config(sources=["task_history"])
    db = _make_db()
    db.search_similar_tasks = AsyncMock(return_value=[
        {
            "id": "t1",
            "title": "Deploy backend",
            "status": "completada",
            "updated_at": "2024-02-01T09:00:00Z",
        }
    ])

    memory = Memory(config, db)
    memory.embedder._available = False
    memory._embedder_checked = True

    result = await memory.retrieve({"title": "Deploy service"})
    assert "Deploy backend" in result
    assert "completada" in result


# ── Test: vector retrieve ─────────────────────────────────────

@pytest.mark.asyncio
async def test_vector_retrieve_uses_cosine_similarity():
    """Vector search returns chunks above similarity threshold."""
    config = _make_config()
    db = _make_db()

    # Two stored embeddings: one similar, one orthogonal
    v_query = [1.0, 0.0, 0.0]
    v_similar = [0.9, 0.1, 0.0]  # high cosine with v_query
    v_different = [0.0, 1.0, 0.0]  # orthogonal

    db.get_all_embeddings = AsyncMock(return_value=[
        {"id": "c1", "source_type": "note", "source_id": "n1",
         "content": "Relevant content about auth", "embedding": v_similar},
        {"id": "c2", "source_type": "note", "source_id": "n2",
         "content": "Unrelated content", "embedding": v_different},
    ])

    memory = Memory(config, db)
    memory.embedder._available = True
    memory._embedder_checked = True
    memory.embedder.embed = AsyncMock(return_value=v_query)

    chunks = await memory._vector_retrieve("auth token")
    # The similar chunk should be in results, the orthogonal one should not
    assert any("Relevant content" in c for c in chunks)
    # cosine([1,0,0], [0,1,0]) = 0.0, below 0.3 threshold
    assert not any("Unrelated content" in c for c in chunks)


@pytest.mark.asyncio
async def test_vector_retrieve_returns_empty_when_embed_fails():
    """If embedding fails, vector retrieve returns empty list."""
    config = _make_config()
    db = _make_db()
    db.get_all_embeddings = AsyncMock(return_value=[
        {"id": "c1", "source_type": "note", "source_id": "n1",
         "content": "Some content", "embedding": [1.0, 0.0]},
    ])

    memory = Memory(config, db)
    memory.embedder._available = True
    memory._embedder_checked = True
    memory.embedder.embed = AsyncMock(return_value=None)  # embed failed

    chunks = await memory._vector_retrieve("query")
    assert chunks == []


# ── Test: index_unembedded ────────────────────────────────────

@pytest.mark.asyncio
async def test_index_unembedded_skips_when_disabled():
    config = _make_config(enabled=False)
    db = _make_db()
    memory = Memory(config, db)

    count = await memory.index_unembedded()
    assert count == 0
    db.get_unembedded_notes.assert_not_called()


@pytest.mark.asyncio
async def test_index_unembedded_skips_when_ollama_unavailable():
    config = _make_config()
    db = _make_db()
    db.get_unembedded_notes = AsyncMock(return_value=[
        {"id": "n1", "title": "Note A", "content": "Content A", "type": "nota"}
    ])

    memory = Memory(config, db)
    memory.embedder._available = False
    memory._embedder_checked = True

    count = await memory.index_unembedded()
    assert count == 0
    db.store_embedding.assert_not_called()


@pytest.mark.asyncio
async def test_index_unembedded_stores_embeddings():
    config = _make_config()
    db = _make_db()
    db.get_unembedded_notes = AsyncMock(return_value=[
        {"id": "n1", "title": "Note A", "content": "Content A", "type": "nota"},
        {"id": "n2", "title": "Decision B", "content": "Content B", "type": "decision"},
    ])

    memory = Memory(config, db)
    memory.embedder._available = True
    memory._embedder_checked = True
    memory.embedder.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])

    count = await memory.index_unembedded()
    assert count == 2
    assert db.store_embedding.call_count == 2

    # Check source_type mapping
    calls = db.store_embedding.call_args_list
    source_types = [c.kwargs["source_type"] for c in calls]
    assert "note" in source_types
    assert "decision" in source_types
