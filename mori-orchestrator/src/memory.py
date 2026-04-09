"""
memory.py — context retrieval for Mori agents.

Strategy (in priority order):
1. sqlite-vec KNN search if embeddings exist + Ollama available
2. SQLite FTS5 BM25 search (always available)
3. Empty string (no context)

Auto-indexer: on startup, runs in background to embed unembedded notes.
"""
from __future__ import annotations

import asyncio
import json
import math
import struct
from typing import TYPE_CHECKING

import aiohttp
import structlog

if TYPE_CHECKING:
    from .config import MoriConfig, MemoryConfig
    from .db import Database

log = structlog.get_logger(__name__)


# ── Cosine similarity (pure Python, no numpy needed) ─────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ── Ollama embedding client ───────────────────────────────────

class OllamaEmbedder:
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._available: bool | None = None  # None = not checked yet

    async def check_available(self) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/tags", timeout=aiohttp.ClientTimeout(total=3)) as r:
                    if r.status == 200:
                        data = await r.json()
                        models = [m["name"] for m in data.get("models", [])]
                        self._available = any(self.model in m for m in models)
                    else:
                        self._available = False
        except Exception:
            self._available = False
        log.info("ollama_available", available=self._available, model=self.model)
        return self._available

    async def embed(self, text: str) -> list[float] | None:
        if self._available is False:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        return data.get("embedding")
        except Exception as e:
            log.warning("ollama_embed_failed", error=str(e))
        return None


# ── TF-IDF fallback (pure Python) ────────────────────────────

def tfidf_score(query: str, document: str) -> float:
    """Simple TF-IDF score between query and document (bag of words)."""
    query_terms = set(query.lower().split())
    doc_terms = document.lower().split()
    if not doc_terms:
        return 0.0
    tf = sum(1 for t in doc_terms if t in query_terms) / len(doc_terms)
    return tf


# ── Main Memory class ─────────────────────────────────────────

class Memory:
    def __init__(self, config: "MoriConfig", db: "Database"):
        self.config = config
        self.db = db
        mem_cfg = config.memory

        # Find Ollama base_url from models config
        ollama_url = "http://localhost:11434"
        for model in config.models:
            if model.provider == "ollama" and model.base_url:
                ollama_url = model.base_url
                break

        self.embedder = OllamaEmbedder(ollama_url, mem_cfg.embedding_model)
        self._embedder_checked = False

    async def retrieve(self, task: dict) -> str:
        """Retrieve relevant context for a task."""
        if not self.config.memory.enabled:
            return ""

        query = self._build_query(task)
        if not query.strip():
            return ""

        chunks: list[str] = []

        # Try vector search first
        if not self._embedder_checked:
            await self.embedder.check_available()
            self._embedder_checked = True

        if self.embedder._available:
            chunks = await self._vector_retrieve(query)

        # Fall back to FTS5 if no vector results
        if not chunks:
            chunks = await self._fts_retrieve(query)

        return "\n".join(chunks[: self.config.memory.top_k])

    async def _vector_retrieve(self, query: str) -> list[str]:
        """KNN search using cosine similarity over stored embeddings."""
        query_embedding = await self.embedder.embed(query)
        if not query_embedding:
            return []

        all_chunks = await self.db.get_all_embeddings()
        if not all_chunks:
            return []

        # Score each chunk
        scored = []
        for chunk in all_chunks:
            if chunk.get("embedding"):
                sim = cosine_similarity(query_embedding, chunk["embedding"])
                scored.append((sim, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: self.config.memory.top_k]

        result = []
        for sim, chunk in top:
            if sim < 0.3:  # threshold
                continue
            source_label = chunk["source_type"].capitalize()
            result.append(f"[{source_label}] {chunk['content'][:400]} (relevancia: {sim:.2f})")

        return result

    async def _fts_retrieve(self, query: str) -> list[str]:
        """FTS5 BM25 search as fallback."""
        chunks = []

        if "notes" in self.config.memory.sources or "decisions" in self.config.memory.sources:
            notes = await self.db.search_notes_fts(query, limit=self.config.memory.top_k)
            for note in notes:
                note_type = note.get("type", "nota")
                label = "Decisión" if note_type == "decision" else "Nota"
                chunks.append(f"[{label} - {note.get('updated_at','')[:10]}] {note['title']}: {note.get('content','')[:300]}")

        if "task_history" in self.config.memory.sources:
            similar = await self.db.search_similar_tasks(query, limit=3)
            for t in similar:
                chunks.append(f"[Tarea similar - {t.get('updated_at','')[:10]}] {t['title']} → {t['status']}")

        return chunks

    def _build_query(self, task: dict) -> str:
        parts = [task.get("title", "")]
        if task.get("description"):
            parts.append(task["description"])
        tags = task.get("tags") or []
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = []
        parts.extend(tags)
        return " ".join(p for p in parts if p)

    # ── Background indexer ─────────────────────────────────────

    async def index_unembedded(self) -> int:
        """Index notes that don't have embeddings yet. Returns count indexed."""
        if not self.config.memory.enabled:
            return 0

        if not self._embedder_checked:
            await self.embedder.check_available()
            self._embedder_checked = True

        if not self.embedder._available:
            return 0

        notes = await self.db.get_unembedded_notes(limit=20)
        count = 0

        for note in notes:
            text = f"{note['title']} {note.get('content', '')}"
            embedding = await self.embedder.embed(text)
            if embedding:
                source_type = "decision" if note.get("type") == "decision" else "note"
                await self.db.store_embedding(
                    source_type=source_type,
                    source_id=note["id"],
                    content=text[:500],
                    embedding=embedding,
                    model=self.embedder.model,
                )
                count += 1
                await asyncio.sleep(0.1)  # don't hammer Ollama

        if count:
            log.info("indexed_notes", count=count)
        return count

    async def run_background_indexer(self) -> None:
        """Run periodically to keep embeddings up to date."""
        while True:
            try:
                await self.index_unembedded()
            except Exception as e:
                log.warning("indexer_error", error=str(e))
            await asyncio.sleep(300)  # every 5 minutes

    # ── Write helpers ─────────────────────────────────────────

    async def store_decision(
        self,
        project_id: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> None:
        """
        Placeholder for persisting decisions/notes produced by the agent.
        Currently a no-op — extend by inserting into a decisions table.
        """
        log.debug(
            "decision_store_called",
            project_id=project_id,
            title=title,
            note="decisions table not yet implemented",
        )
