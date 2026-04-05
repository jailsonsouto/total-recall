"""
indexer.py — Motor de indexação delta-based para Codex
=======================================================

Orquestra: discover → parse → embed → store.
Cada sessão é indexada dentro de uma transação atômica.
"""

import json
from datetime import datetime
from typing import Optional

from .database import Database
from .embeddings import EmbeddingProvider
from .models import SessionInfo, Chunk
from .session_discovery import discover_sessions
from .session_parser import parse_codex_session
from .vector_store import SQLiteVectorStore


class Indexer:
    """Indexa sessões JSONL do Codex em SQLite com delta tracking."""

    def __init__(self, db: Database, vector_store: SQLiteVectorStore,
                 embed_provider: Optional[EmbeddingProvider] = None):
        self.db = db
        self.vector_store = vector_store
        self.embed = embed_provider

    def index_all(self, full: bool = False,
                  session_ids: Optional[list[str]] = None) -> dict:
        """
        Executa indexação incremental (ou full).

        Returns dict com: files_scanned, files_indexed, chunks_created, errors.
        """
        report = {
            "files_scanned": 0,
            "files_indexed": 0,
            "chunks_created": 0,
            "errors": [],
        }

        run_id = None
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO indexing_runs (started_at) VALUES (?)",
                [datetime.now().isoformat()],
            )
            run_id = cursor.lastrowid

        if full:
            with self.db.transaction() as conn:
                conn.execute("DELETE FROM chunks_fts")
                conn.execute("DELETE FROM chunks")
                conn.execute("DELETE FROM sessions")
                conn.execute("DELETE FROM embedding_cache")
            self.db.recreate_vec_table()

        sessions = discover_sessions(session_ids=session_ids)
        report["files_scanned"] = len(sessions)

        for sess in sessions:
            file_path = sess["file_path"]
            session_id = sess["session_id"]
            file_hash = sess["file_hash"]
            project_label = sess["project_label"]

            try:
                # Check if already indexed with same hash
                if not full:
                    with self.db.connection() as conn:
                        row = conn.execute(
                            "SELECT file_hash FROM sessions WHERE session_id = ?",
                            [session_id],
                        ).fetchone()
                        if row and row["file_hash"] == file_hash:
                            report["files_scanned"]  # scanned but not indexed
                            continue

                session_info, chunks = parse_codex_session(file_path)

                # Override project_label from discovery if parser didn't get it
                if project_label and project_label != "unknown":
                    session_info.project_label = project_label

                embed_model = self.embed.model_name if self.embed else "none"
                has_embedding = self.embed is not None

                # Check for append-only (file grew)
                skip_until = -1
                if not full:
                    with self.db.connection() as conn:
                        row = conn.execute(
                            "SELECT MAX(chunk_index) FROM chunks WHERE session_id = ?",
                            [session_id],
                        ).fetchone()
                        if row and row[0] is not None:
                            skip_until = row[0]

                chunks_inserted = self._insert_session(
                    session_info, chunks, file_hash,
                    embed_model, has_embedding, skip_until,
                )

                report["files_indexed"] += 1
                report["chunks_created"] += chunks_inserted

            except Exception as e:
                error_msg = f"{file_path}: {str(e)}"
                report["errors"].append(error_msg)

        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE indexing_runs SET ended_at = ?, files_scanned = ?, "
                "files_indexed = ?, chunks_created = ?, errors = ? WHERE id = ?",
                [datetime.now().isoformat(), report["files_scanned"],
                 report["files_indexed"], report["chunks_created"],
                 json.dumps(report["errors"], ensure_ascii=False), run_id],
            )

        return report

    def _insert_session(self, session_info: SessionInfo, chunks: list[Chunk],
                        file_hash: str, embed_model: str,
                        has_embedding: bool, skip_until: int = -1) -> int:
        """Insere sessão e chunks no banco. Retorna chunks novos inseridos."""
        count = 0

        with self.db.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions "
                "(session_id, project_path, project_label, title, "
                " started_at, ended_at, user_messages, asst_messages, "
                " file_path, file_hash, file_size, is_subagent, "
                " parent_session_id, indexed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [session_info.session_id, session_info.project_path,
                 session_info.project_label, session_info.title,
                 session_info.started_at.isoformat() if session_info.started_at else None,
                 session_info.ended_at.isoformat() if session_info.ended_at else None,
                 session_info.user_messages, session_info.asst_messages,
                 session_info.file_path, file_hash,
                 session_info.file_size, session_info.is_subagent,
                 session_info.parent_session_id,
                 datetime.now().isoformat()],
            )

            for chunk in chunks:
                if chunk.chunk_index <= skip_until:
                    continue

                self.vector_store.add(
                    session_id=session_info.session_id,
                    role=chunk.role,
                    content=chunk.content,
                    timestamp=chunk.timestamp.isoformat() if chunk.timestamp else None,
                    chunk_index=chunk.chunk_index,
                    line_start=chunk.line_start,
                    line_end=chunk.line_end,
                    has_embedding=has_embedding,
                    embed_model=embed_model,
                    metadata=chunk.metadata,
                    _conn=conn,
                )
                count += 1

                # Graph Lite: indexa entidades do chunk
                entities = chunk.metadata.get("entities", []) if chunk.metadata else []
                if entities:
                    self._index_entities(conn, count, entities)

        return count

    def _index_entities(self, conn, chunk_id: int, entities: list[str]):
        """Insere entidades no graph lite (entidades + chunk_entities)."""
        for entity_name in entities:
            # Normaliza: lowercase para consistência
            name = entity_name.strip()
            if not name or len(name) < 2:
                continue

            # Determina tipo baseado no padrão
            entity_type = "term"
            if name.startswith("ADR"):
                entity_type = "decision"
            elif name.isupper() and len(name) <= 4:
                entity_type = "acronym"
            elif name[0].isupper():
                entity_type = "technology"

            # Insert or ignore entidade
            conn.execute(
                "INSERT OR IGNORE INTO entities (name, type) VALUES (?, ?)",
                [name, entity_type],
            )

            # Link chunk → entidade
            entity_id = conn.execute(
                "SELECT id FROM entities WHERE name = ?", [name]
            ).fetchone()[0]

            conn.execute(
                "INSERT OR IGNORE INTO chunk_entities (chunk_id, entity_id) VALUES (?, ?)",
                [chunk_id, entity_id],
            )
