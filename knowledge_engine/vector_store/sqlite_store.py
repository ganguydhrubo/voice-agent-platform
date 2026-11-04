"""Chunk storage and search in SQLite: NumPy for vectors, FTS5 for words.

A brute-force scan over a few thousand chunks takes single-digit milliseconds on a laptop, so an
external vector database is not needed at this size. Every read takes tenant_id and kb_ids and
filters on them in SQL, which is what keeps one customer's documents away from another's.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass

import numpy as np

from backend.db import Database, new_id
from knowledge_engine.ingestion.chunker import Chunk
from knowledge_engine.text import fold


@dataclass(frozen=True)
class StoredChunk:
    id: str
    document_id: str
    kb_id: str
    title: str
    section: str
    language: str
    text: str
    flagged: bool


class ChunkStore:
    def __init__(self, db: Database, dimensions: int) -> None:
        self._db = db
        self._dimensions = dimensions
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, str], tuple[list[str], np.ndarray]] = {}

    def add(
        self, tenant_id: str, kb_id: str, document_id: str, chunks: list[Chunk], vectors: np.ndarray
    ) -> None:
        rows = [
            (
                new_id(),
                tenant_id,
                kb_id,
                document_id,
                chunk.ordinal,
                chunk.section,
                chunk.language,
                chunk.text,
                fold(chunk.text),
                int(chunk.flagged),
                vector.astype(np.float32).tobytes(),
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        self._db.executemany(
            "INSERT INTO chunks (id, tenant_id, kb_id, document_id, ordinal, section, language, text, search_text,"
            " flagged, embedding) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self.invalidate(tenant_id, kb_id)

    def invalidate(self, tenant_id: str, kb_id: str) -> None:
        with self._lock:
            self._cache.pop((tenant_id, kb_id), None)

    def _matrix(self, tenant_id: str, kb_id: str) -> tuple[list[str], np.ndarray]:
        key = (tenant_id, kb_id)
        with self._lock:
            cached = self._cache.get(key)
        if cached:
            return cached
        rows = self._db.all(
            "SELECT id, embedding FROM chunks WHERE tenant_id = ? AND kb_id = ? AND flagged = 0",
            (tenant_id, kb_id),
        )
        ids = [row["id"] for row in rows]
        matrix = (
            np.vstack([np.frombuffer(row["embedding"], dtype=np.float32) for row in rows])
            if rows
            else np.zeros((0, self._dimensions), np.float32)
        )
        with self._lock:
            self._cache[key] = (ids, matrix)
        return ids, matrix

    def dense_search(
        self, tenant_id: str, kb_ids: list[str], vector: np.ndarray, limit: int
    ) -> list[tuple[str, float]]:
        scored: list[tuple[str, float]] = []
        for kb_id in kb_ids:
            ids, matrix = self._matrix(tenant_id, kb_id)
            if not ids:
                continue
            scores = matrix @ vector
            for index in np.argsort(-scores)[:limit]:
                scored.append((ids[int(index)], float(scores[int(index)])))
        scored.sort(key=lambda item: -item[1])
        return scored[:limit]

    def lexical_search(
        self, tenant_id: str, kb_ids: list[str], query: str, limit: int
    ) -> list[tuple[str, float]]:
        terms = fts_terms(query)
        if not terms or not kb_ids:
            return []
        marks = ",".join("?" for _ in kb_ids)
        rows = self._db.all(
            "SELECT c.id AS id, bm25(chunks_fts) AS rank FROM chunks_fts"
            " JOIN chunks c ON c.rowid_key = chunks_fts.rowid"
            f" WHERE chunks_fts MATCH ? AND c.tenant_id = ? AND c.kb_id IN ({marks}) AND c.flagged = 0"
            " ORDER BY rank LIMIT ?",
            (" OR ".join(terms), tenant_id, *kb_ids, limit),
        )
        return [(row["id"], -float(row["rank"])) for row in rows]

    def fetch(self, tenant_id: str, chunk_ids: list[str]) -> dict[str, StoredChunk]:
        if not chunk_ids:
            return {}
        marks = ",".join("?" for _ in chunk_ids)
        rows = self._db.all(
            "SELECT c.id, c.document_id, c.kb_id, d.title, c.section, c.language, c.text, c.flagged"
            " FROM chunks c JOIN documents d ON d.id = c.document_id"
            f" WHERE c.tenant_id = ? AND c.id IN ({marks})",
            (tenant_id, *chunk_ids),
        )
        return {
            row["id"]: StoredChunk(
                row["id"],
                row["document_id"],
                row["kb_id"],
                row["title"],
                row["section"],
                row["language"],
                row["text"],
                bool(row["flagged"]),
            )
            for row in rows
        }


_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_STOPWORDS = frozenset(
    "a an and are as at be by can do does for from has have how i in is it me my of on or our the "
    "their there this to was we what when where which who why will with you your".split()
)
# Question and helper words in Hindi and Bengali, in their folded form.
_STOPWORDS |= {fold(word) for word in (
    "क्या कब कहाँ कहां कैसे कौन कितना कितने कितनी है हैं हूँ का की के को में से पर और या यह वह वो मैं आप हम कुछ क्यों नहीं करते करता करती करना करें करो हो था थी थे वे उस उसे इस इसे तो भी ही कि जो तक लिए साथ बहुत "
    "কোথায় কখন কী কি কেন কীভাবে কত কে এটা ওটা এই সেই আমি আপনি আমরা আছে হয় এবং বা থেকে না নয় করে করেন কিছু কেউ তিনি তারা সে যে তো তার এর জন্য সঙ্গে ছিল ছিলেন হবে হয়েছে"
).split()}


def fts_terms(query: str) -> list[str]:
    """Quoted terms for FTS5, so words in the query can never act as FTS operators."""
    words = []
    for word in re.findall(r"[\wऀ-ॿঀ-৿]+", fold(query)):
        if word in _STOPWORDS or len(word) < 2:
            continue
        words.append('"' + word.replace('"', "") + '"')
    return list(dict.fromkeys(words))[:24]
