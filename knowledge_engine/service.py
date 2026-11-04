"""Ingestion pipeline: parse, clean, chunk, embed, store. Search is scoped to one tenant."""
from __future__ import annotations

import hashlib

from backend.db import Database, new_id, now_iso
from knowledge_engine.ingestion.chunker import chunk_sections
from knowledge_engine.ingestion.parsers import IngestionError, Section, parse_bytes, parse_faq
from knowledge_engine.retrieval.retriever import Retrieval, Retriever
from knowledge_engine.vector_store.sqlite_store import ChunkStore


class KnowledgeService:
    def __init__(self, db: Database, embedder) -> None:
        self._db = db
        self._embedder = embedder
        self.store = ChunkStore(db, embedder.dimensions)
        self.retriever = Retriever(self.store, embedder)

    def create_base(self, tenant_id: str, name: str, description: str = "") -> dict:
        base = {
            "id": new_id(),
            "tenant_id": tenant_id,
            "name": name,
            "description": description,
            "created_at": now_iso(),
        }
        self._db.execute(
            "INSERT INTO knowledge_bases (id, tenant_id, name, description, created_at) VALUES (?, ?, ?, ?, ?)",
            tuple(base.values()),
        )
        return base

    def _require_base(self, tenant_id: str, kb_id: str) -> None:
        if not self._db.one("SELECT id FROM knowledge_bases WHERE id = ? AND tenant_id = ?", (kb_id, tenant_id)):
            raise IngestionError("Knowledge base not found.")

    def _store_sections(
        self, tenant_id: str, kb_id: str, title: str, kind: str, source_ref: str, sections: list[Section], digest: str
    ) -> dict:
        self._require_base(tenant_id, kb_id)
        if self._db.one("SELECT id FROM documents WHERE kb_id = ? AND sha256 = ?", (kb_id, digest)):
            raise IngestionError("This document is already in the knowledge base.")
        document_id = new_id()
        self._db.execute(
            "INSERT INTO documents (id, tenant_id, kb_id, title, source_type, source_ref, sha256, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'processing', ?)",
            (document_id, tenant_id, kb_id, title, kind, source_ref, digest, now_iso()),
        )
        try:
            chunks = chunk_sections(sections)
            if not chunks:
                raise IngestionError("No usable text was found.")
            vectors = self._embedder.embed_passages([chunk.text for chunk in chunks])
            self.store.add(tenant_id, kb_id, document_id, chunks, vectors)
        except Exception as error:
            self._db.execute(
                "UPDATE documents SET status = 'failed', error = ? WHERE id = ?",
                (str(error)[:300], document_id),
            )
            raise
        flagged = sum(1 for chunk in chunks if chunk.flagged)
        self._db.execute(
            "UPDATE documents SET status = 'ready', chunk_count = ? WHERE id = ?",
            (len(chunks), document_id),
        )
        return {"id": document_id, "title": title, "chunks": len(chunks), "flagged_chunks": flagged}

    def ingest_file(self, tenant_id: str, kb_id: str, filename: str, data: bytes) -> dict:
        kind, sections = parse_bytes(filename, data)
        return self._store_sections(
            tenant_id, kb_id, filename[:200], kind, filename[:200], sections, hashlib.sha256(data).hexdigest()
        )

    def ingest_sections(self, tenant_id: str, kb_id: str, url: str, sections: list[Section]) -> dict:
        digest = hashlib.sha256("".join(section.text for section in sections).encode()).hexdigest()
        return self._store_sections(tenant_id, kb_id, sections[0].title, "url", url[:500], sections, digest)

    def ingest_faq(self, tenant_id: str, kb_id: str, title: str, pairs: list[dict]) -> dict:
        sections = parse_faq(pairs)
        digest = hashlib.sha256("".join(section.text for section in sections).encode()).hexdigest()
        return self._store_sections(tenant_id, kb_id, title, "faq", "", sections, digest)

    def delete_document(self, tenant_id: str, document_id: str) -> bool:
        row = self._db.one(
            "SELECT kb_id FROM documents WHERE id = ? AND tenant_id = ?", (document_id, tenant_id)
        )
        if not row:
            return False
        self._db.execute("DELETE FROM chunks WHERE document_id = ? AND tenant_id = ?", (document_id, tenant_id))
        self._db.execute("DELETE FROM documents WHERE id = ? AND tenant_id = ?", (document_id, tenant_id))
        self.store.invalidate(tenant_id, row["kb_id"])
        return True

    def delete_base(self, tenant_id: str, kb_id: str) -> bool:
        if not self._db.one("SELECT id FROM knowledge_bases WHERE id = ? AND tenant_id = ?", (kb_id, tenant_id)):
            return False
        self._db.execute("DELETE FROM chunks WHERE kb_id = ? AND tenant_id = ?", (kb_id, tenant_id))
        self._db.execute("DELETE FROM knowledge_bases WHERE id = ? AND tenant_id = ?", (kb_id, tenant_id))
        self.store.invalidate(tenant_id, kb_id)
        return True

    def search(self, tenant_id: str, kb_ids: list[str], query: str, language: str = "", limit: int = 3) -> Retrieval:
        return self.retriever.search(tenant_id, kb_ids, query, language, limit)
