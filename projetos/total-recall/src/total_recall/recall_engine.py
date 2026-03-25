"""
recall_engine.py — Motor de busca com temporal decay + MMR
==========================================================

Camada de inteligência sobre o vector_store:
  1. Busca híbrida (vetor 70% + FTS5 30%)
  2. Temporal decay (sessões recentes pesam mais)
  3. MMR re-ranking (diversidade nos resultados)
"""

import math
from datetime import datetime, timezone
from typing import Optional

from .config import DECAY_HALF_LIFE_DAYS, MMR_LAMBDA
from .database import Database
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

        # Aplica peso por role (thinking/tool_context pesam menos)
        _ROLE_WEIGHTS = {
            "exchange": 1.0,
            "user": 1.0,
            "assistant": 1.0,
            "thinking": 0.6,
            "tool_context": 0.7,
        }
        for r in candidates:
            r.score *= _ROLE_WEIGHTS.get(r.role, 1.0)

        # Aplica temporal decay
        now = datetime.now(timezone.utc)
        for r in candidates:
            is_architectural = self._detect_architectural(r.content)
            r.score = self._temporal_decay(r.score, r.timestamp, now, is_architectural)

        # MMR re-ranking
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

        Evita retornar 5 chunks da mesma sessão sobre o mesmo tema.
        Usa Jaccard similarity no texto tokenizado.
        """
        if len(candidates) <= limit:
            return sorted(candidates, key=lambda r: r.score, reverse=True)

        # Tokeniza cada candidato
        tokens_list = [set(r.content.lower().split()) for r in candidates]

        selected = []
        remaining = list(range(len(candidates)))

        for _ in range(limit):
            best_idx = -1
            best_mmr = -float("inf")

            for idx in remaining:
                relevance = candidates[idx].score

                # Max similaridade com já selecionados
                max_sim = 0.0
                for sel_idx in [s[0] for s in selected]:
                    sim = self._jaccard(tokens_list[idx], tokens_list[sel_idx])
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

    @staticmethod
    def _jaccard(set_a: set, set_b: set) -> float:
        """Similaridade de Jaccard entre dois conjuntos de tokens."""
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0
