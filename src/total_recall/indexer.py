"""
indexer.py — Motor de indexação delta-based
============================================

Orquestra: discover → parse → embed → store.
Cada sessão é indexada dentro de uma transação atômica.
"""

import json
from datetime import datetime
from typing import Optional

from .database import Database
from .embeddings import EmbeddingProvider
from .models import SessionInfo, Chunk
from .session_discovery import SessionDiscovery, DiscoveredFile
from .session_parser import SessionParser
from .vector_store import SQLiteVectorStore


class Indexer:
    """Indexa sessões JSONL em SQLite com delta tracking."""

    def __init__(self, db: Database, vector_store: SQLiteVectorStore,
                 embed_provider: Optional[EmbeddingProvider],
                 discovery: SessionDiscovery):
        self.db = db
        self.vector_store = vector_store
        self.embed = embed_provider
        self.discovery = discovery

    def index(self, full: bool = False) -> dict:
        """
        Executa indexação incremental (ou full).

        Retorna dict com: files_scanned, files_indexed,
        files_skipped, chunks_created, errors.
        """
        report = {
            "files_scanned": 0,
            "files_indexed": 0,
            "files_skipped": 0,
            "chunks_created": 0,
            "errors": [],
        }

        # Registra run
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO indexing_runs (started_at) VALUES (?)",
                [datetime.now().isoformat()],
            )
            run_id = cursor.lastrowid

        # Descobre arquivos
        if full:
            # Full: limpa tudo e redescobre
            with self.db.transaction() as conn:
                conn.execute("DELETE FROM chunks_fts")
                conn.execute("DELETE FROM chunks_vec")
                conn.execute("DELETE FROM chunks")
                conn.execute("DELETE FROM sessions")
            files = self.discovery.discover()
        else:
            files = self.discovery.get_changed_files()

        all_discovered = self.discovery.discover()
        report["files_scanned"] = len(all_discovered)

        import sys
        for discovered in files:
            try:
                # Se é "changed", limpa dados antigos
                if discovered.status == "changed":
                    self._delete_session_data(discovered)

                chunks_count = self._index_single_file(discovered)
                report["files_indexed"] += 1
                report["chunks_created"] += chunks_count

                print(
                    f"  Indexado: {discovered.path.name} "
                    f"({chunks_count} chunks)",
                    file=sys.stderr,
                )

            except Exception as e:
                error_msg = f"{discovered.path.name}: {str(e)}"
                report["errors"].append(error_msg)
                print(f"  ERRO: {error_msg}", file=sys.stderr)

        report["files_skipped"] = report["files_scanned"] - report["files_indexed"]

        # Atualiza run
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE indexing_runs SET ended_at = ?, files_scanned = ?, "
                "files_indexed = ?, chunks_created = ?, errors = ? WHERE id = ?",
                [datetime.now().isoformat(), report["files_scanned"],
                 report["files_indexed"], report["chunks_created"],
                 json.dumps(report["errors"], ensure_ascii=False), run_id],
            )

        return report

    def _index_single_file(self, discovered: DiscoveredFile) -> int:
        """Parseia e indexa um arquivo JSONL. Retorna contagem de chunks."""
        parser = SessionParser(discovered.path)
        session_info, chunks = parser.parse()

        embed_model = self.embed.model_name if self.embed else "none"
        has_embedding = self.embed is not None

        with self.db.transaction() as conn:
            # Insere session
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
                 str(discovered.path), discovered.file_hash,
                 session_info.file_size, session_info.is_subagent,
                 session_info.parent_session_id,
                 datetime.now().isoformat()],
            )

            # Insere chunks
            count = 0
            for chunk in chunks:
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

            return count

    def _delete_session_data(self, discovered: DiscoveredFile):
        """Remove dados de uma sessão para reindexação."""
        with self.db.transaction() as conn:
            # Busca session_id pelo file_path
            row = conn.execute(
                "SELECT session_id FROM sessions WHERE file_path = ?",
                [str(discovered.path)],
            ).fetchone()

            if not row:
                return

            sid = row[0]

            # Remove chunks_fts e chunks_vec pelos rowids dos chunks
            chunk_ids = [
                r[0] for r in conn.execute(
                    "SELECT id FROM chunks WHERE session_id = ?", [sid]
                ).fetchall()
            ]

            for cid in chunk_ids:
                conn.execute("DELETE FROM chunks_vec WHERE rowid = ?", [cid])
                conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", [cid])

            conn.execute("DELETE FROM chunks WHERE session_id = ?", [sid])
            conn.execute("DELETE FROM sessions WHERE session_id = ?", [sid])
