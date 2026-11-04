"""Hybrid retrieval: vectors and words are fused, reranked, and given a confidence score."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from knowledge_engine.text import fold
from knowledge_engine.vector_store.sqlite_store import ChunkStore, StoredChunk, fts_terms

RRF_K = 60


@dataclass(frozen=True)
class Hit:
    chunk: StoredChunk
    score: float
    cosine: float
    coverage: float

    def source(self) -> dict:
        return {
            "document_id": self.chunk.document_id,
            "title": self.chunk.title,
            "section": self.chunk.section,
            "score": round(self.score, 3),
        }


@dataclass(frozen=True)
class Retrieval:
    hits: list[Hit]
    confidence: float

    def to_dict(self) -> dict:
        return {"confidence": self.confidence, "hits": [asdict(hit) for hit in self.hits]}


def term_coverage(query: str, text: str) -> float:
    """Share of the query's meaningful words that appear in the text."""
    terms = [term.strip('"') for term in fts_terms(query)]
    if not terms:
        return 0.0
    lowered = fold(text)
    return sum(1 for term in terms if term in lowered) / len(terms)


class Retriever:
    def __init__(self, store: ChunkStore, embedder) -> None:
        self._store = store
        self._embedder = embedder

    def search(
        self, tenant_id: str, kb_ids: list[str], query: str, language: str = "", limit: int = 3
    ) -> Retrieval:
        if not kb_ids or not query.strip():
            return Retrieval([], 0.0)
        vector: np.ndarray = self._embedder.embed_query(query)
        dense = self._store.dense_search(tenant_id, kb_ids, vector, 20)
        lexical = self._store.lexical_search(tenant_id, kb_ids, query, 20)

        fused: dict[str, float] = {}
        for ranked in (dense, lexical):
            for rank, (chunk_id, _) in enumerate(ranked):
                fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
        chunks = self._store.fetch(tenant_id, list(fused)[:20])
        cosines = dict(dense)

        hits = []
        for chunk_id, chunk in chunks.items():
            cosine = cosines.get(chunk_id, 0.0)
            coverage = term_coverage(query, chunk.text)
            # Rerank: meaning first, exact words next, and a small lift for the caller's own
            # language so the model reads and repeats text it can handle best.
            score = 0.62 * max(cosine, 0.0) + 0.28 * coverage + 0.10 * (chunk.language == language)
            hits.append(Hit(chunk, score, cosine, coverage))
        hits.sort(key=lambda hit: -hit.score)
        best = hits[:limit]
        return Retrieval(best, self.confidence(best))

    @staticmethod
    def confidence(hits: list[Hit]) -> float:
        """0 to 1. Calibrated in tests/benchmarks/rag_eval.py against answerable and unanswerable questions."""
        if not hits:
            return 0.0
        top = hits[0]
        return round(float(min(1.0, 0.75 * max(top.cosine, 0.0) + 0.45 * top.coverage)), 3)
