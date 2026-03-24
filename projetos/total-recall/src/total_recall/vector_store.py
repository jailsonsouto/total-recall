"""
vector_store.py — Busca vetorial + FTS5 (híbrida)
==================================================

Adaptado do padrão do Memória Viva. Três tabelas ligadas por rowid:
  chunks (metadados) ↔ chunks_vec (vetores) ↔ chunks_fts (texto)
"""

import json
import struct
from typing import Optional

from .config import VECTOR_WEIGHT, TEXT_WEIGHT
from .database import Database, serialize_vector
from .embeddings import EmbeddingProvider
from .models import SearchResult


class SQLiteVectorStore:
    """Implementação com sqlite-vec + FTS5 + embedding cache."""

    def __init__(self, db: Database, embed_provider: Optional[EmbeddingProvider]):
        self.db = db
        self.embed = embed_provider

    def _get_cached_embedding(self, conn, text: str) -> Optional[list[float]]:
        if not self.embed:
            return None
        text_hash = self.embed.text_hash(text)
        row = conn.execute(
            "SELECT embedding FROM embedding_cache WHERE text_hash = ?",
            [text_hash],
        ).fetchone()
        if row:
            n = len(row[0]) // 4
            return list(struct.unpack(f"{n}f", row[0]))
        return None

    def _cache_embedding(self, conn, text: str, vector: list[float]):
        if not self.embed:
            return
        text_hash = self.embed.text_hash(text)
        conn.execute(
            "INSERT OR REPLACE INTO embedding_cache "
            "(text_hash, embedding, model) VALUES (?, ?, ?)",
            [text_hash, serialize_vector(vector), self.embed.model_name],
        )

    def _embed_with_cache(self, conn, text: str) -> Optional[list[float]]:
        if not self.embed:
            return None
        cached = self._get_cached_embedding(conn, text)
        if cached:
            return cached
        try:
            vector = self.embed.embed(text)
            self._cache_embedding(conn, text, vector)
            return vector
        except Exception:
            return None

    def add(self, session_id: str, role: str, content: str,
            timestamp: Optional[str], chunk_index: int,
            line_start: Optional[int], line_end: Optional[int],
            has_embedding: bool, embed_model: str,
            metadata: Optional[dict], _conn=None) -> int:
        """Adiciona um chunk às 3 tabelas (chunks + vec + fts)."""

        def _do_add(conn) -> int:
            vector = None
            actual_has_embedding = False

            if has_embedding and self.embed:
                vector = self._embed_with_cache(conn, content)
                actual_has_embedding = vector is not None

            # chunks (metadados)
            cursor = conn.execute(
                "INSERT INTO chunks "
                "(session_id, role, content, timestamp, chunk_index, "
                " line_start, line_end, has_embedding, embed_model, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [session_id, role, content, timestamp, chunk_index,
                 line_start, line_end, actual_has_embedding,
                 embed_model or "", json.dumps(metadata or {}, ensure_ascii=False)],
            )
            rowid = cursor.lastrowid

            # chunks_vec (vetor)
            if vector:
                conn.execute(
                    "INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
                    [rowid, serialize_vector(vector)],
                )

            # chunks_fts (texto indexado)
            conn.execute(
                "INSERT INTO chunks_fts (rowid, content, session_id, role) "
                "VALUES (?, ?, ?, ?)",
                [rowid, content, session_id, role],
            )

            return rowid

        if _conn:
            return _do_add(_conn)
        with self.db.transaction() as conn:
            return _do_add(conn)

    def search(self, query: str, n_results: int = 5,
               session_id: Optional[str] = None) -> list[SearchResult]:
        """Busca semântica por proximidade vetorial."""
        if not self.embed:
            return []

        try:
            query_vector = self.embed.embed(query)
        except Exception:
            return []

        with self.db.connection() as conn:
            fetch_limit = n_results * 3
            vec_rows = conn.execute(
                "SELECT rowid, distance FROM chunks_vec "
                "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                [serialize_vector(query_vector), fetch_limit],
            ).fetchall()

            if not vec_rows:
                return []

            results = []
            for row in vec_rows:
                rowid, distance = row[0], row[1]
                meta = conn.execute(
                    "SELECT c.content, c.session_id, c.role, c.timestamp, c.metadata, "
                    "       s.title, s.project_label "
                    "FROM chunks c JOIN sessions s ON c.session_id = s.session_id "
                    "WHERE c.id = ?",
                    [rowid],
                ).fetchone()

                if not meta:
                    continue
                if session_id and meta["session_id"] != session_id:
                    continue

                from .session_parser import _parse_timestamp
                results.append(SearchResult(
                    content=meta["content"],
                    session_id=meta["session_id"],
                    role=meta["role"],
                    timestamp=_parse_timestamp(meta["timestamp"]) if meta["timestamp"] else None,
                    distance=distance,
                    score=1.0 / (1.0 + distance),
                    metadata=json.loads(meta["metadata"]) if meta["metadata"] else {},
                    session_title=meta["title"] or "",
                    project_label=meta["project_label"] or "",
                ))

                if len(results) >= n_results:
                    break

            return results

    def keyword_search(self, query: str, n_results: int = 5,
                       session_id: Optional[str] = None) -> list[SearchResult]:
        """Busca por palavra-chave via FTS5."""
        # Sanitiza a query para FTS5: wrap em aspas se contém operadores
        safe_query = self._sanitize_fts_query(query)

        with self.db.connection() as conn:
            try:
                fts_rows = conn.execute(
                    "SELECT rowid, rank FROM chunks_fts "
                    "WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
                    [safe_query, n_results * 3],
                ).fetchall()
            except Exception:
                # Se FTS query falha, tenta busca simples com LIKE
                return self._fallback_like_search(conn, query, n_results, session_id)

            if not fts_rows:
                return []

            results = []
            for row in fts_rows:
                rowid, rank = row[0], abs(row[1])
                meta = conn.execute(
                    "SELECT c.content, c.session_id, c.role, c.timestamp, c.metadata, "
                    "       s.title, s.project_label "
                    "FROM chunks c JOIN sessions s ON c.session_id = s.session_id "
                    "WHERE c.id = ?",
                    [rowid],
                ).fetchone()

                if not meta:
                    continue
                if session_id and meta["session_id"] != session_id:
                    continue

                from .session_parser import _parse_timestamp
                results.append(SearchResult(
                    content=meta["content"],
                    session_id=meta["session_id"],
                    role=meta["role"],
                    timestamp=_parse_timestamp(meta["timestamp"]) if meta["timestamp"] else None,
                    distance=rank,
                    score=1.0 / (1.0 + rank),
                    metadata=json.loads(meta["metadata"]) if meta["metadata"] else {},
                    session_title=meta["title"] or "",
                    project_label=meta["project_label"] or "",
                ))

                if len(results) >= n_results:
                    break

            return results

    def hybrid_search(self, query: str, n_results: int = 5,
                      session_id: Optional[str] = None,
                      vector_weight: float = VECTOR_WEIGHT,
                      text_weight: float = TEXT_WEIGHT) -> list[SearchResult]:
        """Combina busca vetorial + keyword com pesos configuráveis."""
        vector_results = self.search(query, n_results * 2, session_id)
        keyword_results = self.keyword_search(query, n_results * 2, session_id)

        scored: dict[str, dict] = {}

        for r in vector_results:
            key = f"{r.session_id}:{r.content[:100]}"
            scored[key] = {
                "result": r,
                "score": vector_weight * r.score,
            }

        for r in keyword_results:
            key = f"{r.session_id}:{r.content[:100]}"
            if key in scored:
                scored[key]["score"] += text_weight * r.score
            else:
                scored[key] = {
                    "result": r,
                    "score": text_weight * r.score,
                }

        ranked = sorted(scored.values(), key=lambda x: x["score"], reverse=True)

        results = []
        for item in ranked[:n_results]:
            r = item["result"]
            r.score = item["score"]
            results.append(r)

        return results

    def _sanitize_fts_query(self, query: str) -> str:
        """Sanitiza query para FTS5 — wrap em aspas se tem caracteres especiais."""
        special = set('(){}[]^*:!"\'')
        if any(c in special for c in query):
            escaped = query.replace('"', '""')
            return f'"{escaped}"'
        # Se parece query natural, usa OR entre palavras
        words = query.split()
        if len(words) > 1:
            return " OR ".join(f'"{w}"' for w in words if len(w) > 2)
        return query

    def _fallback_like_search(self, conn, query: str, n_results: int,
                              session_id: Optional[str]) -> list[SearchResult]:
        """Fallback com LIKE quando FTS5 falha."""
        sql = (
            "SELECT c.id, c.content, c.session_id, c.role, c.timestamp, c.metadata, "
            "       s.title, s.project_label "
            "FROM chunks c JOIN sessions s ON c.session_id = s.session_id "
            "WHERE c.content LIKE ? "
        )
        params = [f"%{query}%"]
        if session_id:
            sql += "AND c.session_id = ? "
            params.append(session_id)
        sql += "LIMIT ?"
        params.append(n_results)

        rows = conn.execute(sql, params).fetchall()
        results = []
        from .session_parser import _parse_timestamp
        for row in rows:
            results.append(SearchResult(
                content=row["content"],
                session_id=row["session_id"],
                role=row["role"],
                timestamp=_parse_timestamp(row["timestamp"]) if row["timestamp"] else None,
                distance=1.0,
                score=0.5,
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                session_title=row["title"] or "",
                project_label=row["project_label"] or "",
            ))
        return results
