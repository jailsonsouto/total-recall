"""
recall_engine.py — Motor de busca com temporal decay + MMR
==========================================================

Camada de inteligência sobre o vector_store:
  1. Busca híbrida (vetor 70% + FTS5 30%)
  2. Temporal decay (sessões recentes pesam mais)
  3. MMR re-ranking (diversidade nos resultados)
"""

import math
import struct
from datetime import datetime, timezone
from typing import Optional

from .config import DECAY_HALF_LIFE_DAYS, MMR_LAMBDA
from .database import Database, deserialize_vector
from .models import RecallContext, SearchResult
from .vector_store import SQLiteVectorStore


# Palavras que indicam decisões arquiteturais (não decaem)
_DECISION_MARKERS = {
    "decidimos", "decisao", "decisão", "adr", "trade-off", "tradeoff",
    "escolhemos", "optamos", "vs", "instead of", "ao invés de",
    "porque não usar", "porque nao usar", "arquitetura", "architecture",
    "schema", "migração", "migracao",
}


class RecallEngine:
    """Busca inteligente com decay temporal e diversidade."""

    def __init__(self, db: Database, vector_store: SQLiteVectorStore):
        self.db = db
        self.vector_store = vector_store

    def recall(self, query: str, limit: int = 5,
               session_id: Optional[str] = None) -> RecallContext:
        """
        Ponto de entrada principal para /recall.

        1. Busca híbrida (3× candidatos)
        2. Aplica temporal decay
        3. Aplica MMR para diversidade
        4. Retorna RecallContext formatado
        """
        # Resolve session_id prefix → full UUID
        if session_id:
            session_id = self._resolve_session_id(session_id)

        # Stats
        with self.db.connection() as conn:
            sessions_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            chunks_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

        # Busca híbrida (busca mais do que precisa para ter margem)
        candidates, query_info = self.vector_store.hybrid_search(
            query, n_results=limit * 3, session_id=session_id
        )

        if not candidates:
            return RecallContext(
                query=query,
                results=[],
                sessions_searched=sessions_count,
                total_chunks=chunks_count,
                query_info=query_info,
            )

        # Aplica peso por role
        _ROLE_WEIGHTS = {
            "exchange": 1.0,
            "user": 1.0,
            "assistant": 1.0,
            "agent": 0.8,
        }
        for r in candidates:
            r.score *= _ROLE_WEIGHTS.get(r.role, 1.0)

        # Aplica salience scoring: relevance × log(ref+1) × recency_decay
        now = datetime.now(timezone.utc)
        for r in candidates:
            is_architectural = self._detect_architectural(r.content)
            r.score = self._salience_score(r.score, r.timestamp, now, is_architectural)

        # MMR re-ranking (usa embeddings quando disponíveis)
        results = self._mmr_rerank(candidates, limit)

        return RecallContext(
            query=query,
            results=results,
            sessions_searched=sessions_count,
            total_chunks=chunks_count,
            query_info=query_info,
        )

    def _resolve_session_id(self, prefix: str) -> str:
        """Resolve prefixo de session_id para UUID completo."""
        if len(prefix) >= 36:  # já é UUID completo
            return prefix
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT session_id FROM sessions WHERE session_id LIKE ?",
                [prefix + "%"],
            ).fetchone()
            if row:
                return row[0]
        return prefix  # não encontrou, retorna como está

    def _salience_score(self, base_score: float,
                        timestamp: Optional[datetime],
                        now: datetime,
                        is_architectural: bool = False) -> float:
        """
        Salience scoring: relevance × log(ref+1) × recency_decay.

        Inspirado no memU: combina relevância semântica com frequência
        de reforço (aproximada por co-ocorrência de entidades) e recência.

        Decisões arquiteturais NÃO decaem — são atemporais.
        """
        # Temporal decay (herdado do original)
        if is_architectural or not timestamp:
            temporal = 1.0
        else:
            ts = timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_days = (now - ts).total_seconds() / 86400
            if age_days <= 0:
                temporal = 1.0
            else:
                temporal = math.pow(2, -age_days / DECAY_HALF_LIFE_DAYS)

        # Reinforcement factor: log(ref+1)
        # Sem dados de reforço reais ainda, assume ref=1 (cada chunk é "reforçado"
        # por existir no índice). Quando tiver Graph Lite, ref = co-ocorrência count.
        reinforcement = math.log(2)  # log(1+1) = 0.693

        return base_score * reinforcement * temporal

    def _temporal_decay(self, base_score: float,
                        timestamp: Optional[datetime],
                        now: datetime,
                        is_architectural: bool = False) -> float:
        """
        Aplica decay exponencial: score * 2^(-dias / meia_vida).

        Decisões arquiteturais NÃO decaem — são atemporais.
        """
        if is_architectural or not timestamp:
            return base_score

        # Garante timezone-aware
        ts = timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        age_days = (now - ts).total_seconds() / 86400
        if age_days <= 0:
            return base_score

        decay = math.pow(2, -age_days / DECAY_HALF_LIFE_DAYS)
        return base_score * decay

    def _detect_architectural(self, content: str) -> bool:
        """Detecta se o chunk contém uma decisão arquitetural."""
        lower = content.lower()
        return any(marker in lower for marker in _DECISION_MARKERS)

    def _mmr_rerank(self, candidates: list[SearchResult],
                    limit: int) -> list[SearchResult]:
        """
        Maximal Marginal Relevance: seleciona resultados diversos.

        Usa cosine similarity sobre embeddings quando disponíveis —
        detecta redundância semântica real, não apenas sobreposição lexical.
        Faz fallback para Jaccard em chunks sem embedding (modo FTS5-only).

        Penaliza chunks da mesma sessão para forçar cobertura temporal.
        """
        if len(candidates) <= limit:
            return sorted(candidates, key=lambda r: r.score, reverse=True)

        # Carrega embeddings para candidatos que têm chunk_id
        embeddings: dict[int, list[float]] = {}
        chunk_ids = [r.chunk_id for r in candidates if r.chunk_id is not None]
        if chunk_ids:
            with self.db.connection() as conn:
                for chunk_id in chunk_ids:
                    row = conn.execute(
                        "SELECT embedding FROM chunks_vec WHERE rowid = ?",
                        [chunk_id],
                    ).fetchone()
                    if row and row[0]:
                        embeddings[chunk_id] = deserialize_vector(row[0])

        # Tokeniza como fallback para chunks sem embedding
        tokens_list = [set(r.content.lower().split()) for r in candidates]

        selected = []
        remaining = list(range(len(candidates)))

        for _ in range(limit):
            best_idx = -1
            best_mmr = -float("inf")

            for idx in remaining:
                relevance = candidates[idx].score

                max_sim = 0.0
                for sel_idx in [s[0] for s in selected]:
                    sim = self._similarity(
                        candidates[idx], candidates[sel_idx],
                        embeddings, tokens_list, idx, sel_idx,
                    )
                    # Penaliza chunks da mesma sessão: +0.3 na similaridade
                    if candidates[idx].session_id == candidates[sel_idx].session_id:
                        sim = min(1.0, sim + 0.3)
                    if sim > max_sim:
                        max_sim = sim

                mmr = MMR_LAMBDA * relevance - (1 - MMR_LAMBDA) * max_sim
                if mmr > best_mmr:
                    best_mmr = mmr
                    best_idx = idx

            if best_idx >= 0:
                selected.append((best_idx, best_mmr))
                remaining.remove(best_idx)

        return [candidates[idx] for idx, _ in selected]

    def _similarity(self, a: SearchResult, b: SearchResult,
                    embeddings: dict[int, list[float]],
                    tokens_list: list[set],
                    idx_a: int, idx_b: int) -> float:
        """Cosine similarity sobre embeddings; fallback para Jaccard."""
        vec_a = embeddings.get(a.chunk_id) if a.chunk_id else None
        vec_b = embeddings.get(b.chunk_id) if b.chunk_id else None
        if vec_a and vec_b:
            return self._cosine(vec_a, vec_b)
        return self._jaccard(tokens_list[idx_a], tokens_list[idx_b])

    @staticmethod
    def _cosine(vec_a: list[float], vec_b: list[float]) -> float:
        """Cosine similarity entre dois vetores."""
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(x * x for x in vec_a))
        norm_b = math.sqrt(sum(x * x for x in vec_b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _jaccard(set_a: set, set_b: set) -> float:
        """Similaridade de Jaccard entre dois conjuntos de tokens."""
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0
