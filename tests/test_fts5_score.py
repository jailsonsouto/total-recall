"""
tests/test_fts5_score.py — Regressão da fórmula de score do FTS5

Bug real encontrado em produção: `keyword_search()` convertia o rank bruto
do FTS5 em score via `1.0 / (1.0 + rank)`, onde `rank` já é `abs(bm25_rank)`
— e abs(bm25_rank) CRESCE com a força do match (bm25 do SQLite é mais
negativo quanto melhor). A fórmula antiga decrescia com rank maior, então
o match textual mais forte virava o MENOR score do lote — o oposto do
que deveria acontecer. Verificado empiricamente com "aste OR absa": o
melhor match (rank=-9.9275) virava score=0.0915, o 8º melhor (rank=-8.8906)
virava score=0.1011 — maior que o do 1º lugar.

Fix: score = rank / (1.0 + rank) — mesma faixa [0, 1), direção certa.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from total_recall.database import Database
from total_recall.vector_store import SQLiteVectorStore


@pytest.fixture
def db_with_strong_and_weak_match(tmp_path):
    """Dois chunks: um com o termo repetido (match forte, bm25 mais
    negativo), outro com o termo aparecendo 1x num texto longo e diluído
    (match fraco, bm25 menos negativo)."""
    db = Database(db_path=tmp_path / "fts_score.db")
    vector_store = SQLiteVectorStore(db, None)

    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, project_path, file_path, file_hash) "
            "VALUES ('s1', '/tmp', '/tmp/s1.jsonl', 'h1')"
        )

    # Match forte: termo denso, chunk curto
    vector_store.add(
        session_id="s1", role="assistant",
        content="duckdb duckdb duckdb duckdb duckdb perfilamento rápido",
        timestamp=None, chunk_index=0, line_start=None, line_end=None,
        has_embedding=False, embed_model="none", metadata=None,
    )
    # Match fraco: termo aparece 1x, diluído em texto longo irrelevante
    filler = " ".join(["texto", "irrelevante", "sobre", "outra", "coisa"] * 40)
    vector_store.add(
        session_id="s1", role="assistant",
        content=f"{filler} duckdb {filler}",
        timestamp=None, chunk_index=1, line_start=None, line_end=None,
        has_embedding=False, embed_model="none", metadata=None,
    )
    return db, vector_store


class TestFTS5ScoreDirection:
    def test_stronger_match_scores_higher_than_weaker_match(self, db_with_strong_and_weak_match):
        db, vector_store = db_with_strong_and_weak_match
        results, _ = vector_store.keyword_search("duckdb", n_results=5)

        assert len(results) == 2
        strong = next(r for r in results if r.content.startswith("duckdb duckdb"))
        weak = next(r for r in results if not r.content.startswith("duckdb duckdb"))

        assert strong.score > weak.score

    def test_ranked_order_matches_score_order(self, db_with_strong_and_weak_match):
        """O SQL já ordena por `rank` (bm25) ascendente — o score derivado
        precisa preservar essa ordem, não invertê-la."""
        db, vector_store = db_with_strong_and_weak_match
        results, _ = vector_store.keyword_search("duckdb", n_results=5)

        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True), (
            "resultados vêm ordenados por rank (melhor primeiro), "
            "mas os scores não estão na mesma ordem — fórmula invertida"
        )

    def test_score_stays_in_zero_one_range(self, db_with_strong_and_weak_match):
        db, vector_store = db_with_strong_and_weak_match
        results, _ = vector_store.keyword_search("duckdb", n_results=5)
        for r in results:
            assert 0.0 <= r.score < 1.0


# ══════════════════════════════════════════════════════════════
# hybrid_search(): dedup por chunk_id, não por prefixo de texto
# ══════════════════════════════════════════════════════════════
#
# Bug real (só apareceu depois do fix da fórmula acima — a fórmula antiga
# produzia scores tão pequenos que o acúmulo indevido passava despercebido):
# hybrid_search() deduplicava por `f"{session_id}:{content[:100]}"`. Quando
# a mesma sessão tem N chunks DIFERENTES (chunk_id distintos) com os
# mesmos ~100 chars iniciais — ex.: o mesmo README indexado 4x numa
# sessão Codex — o merge `+=` somava a contribuição de texto das 4
# vezes num único resultado. Achado real: score=2.74 numa busca
# "buscla vetorial" (impossível — pesos vector+text somam 1.0).

@pytest.fixture
def db_with_near_duplicate_chunks(tmp_path):
    """4 chunks com os mesmos 100 primeiros caracteres (conteúdo repetido,
    como um README colado várias vezes na mesma sessão) — cada um com
    chunk_id (rowid) diferente."""
    db = Database(db_path=tmp_path / "dedup.db")
    vector_store = SQLiteVectorStore(db, None)

    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, project_path, file_path, file_hash) "
            "VALUES ('s1', '/tmp', '/tmp/s1.jsonl', 'h1')"
        )

    shared_prefix = "ex em SQLite (sqlite-vec + FTS5) com embeddings locais " * 2  # > 100 chars
    for i in range(4):
        vector_store.add(
            session_id="s1", role="assistant",
            content=f"{shared_prefix} variação número {i} do mesmo bloco de texto duckdb",
            timestamp=None, chunk_index=i, line_start=None, line_end=None,
            has_embedding=False, embed_model="none", metadata=None,
        )
    return db, vector_store


class TestHybridSearchDedup:
    def test_near_duplicate_chunks_are_not_summed_together(self, db_with_near_duplicate_chunks):
        db, vector_store = db_with_near_duplicate_chunks
        results, info = vector_store.hybrid_search("duckdb", n_results=10)

        assert len(results) == 4  # 4 chunk_ids distintos, 4 resultados — não fundidos em 1

    def test_combined_score_never_exceeds_theoretical_max(self, db_with_near_duplicate_chunks):
        """vector_weight + text_weight somam 1.0 sempre (0.7/0.3 ou 0.25/0.75)
        — nenhum resultado individual pode ultrapassar isso."""
        db, vector_store = db_with_near_duplicate_chunks
        results, info = vector_store.hybrid_search("duckdb", n_results=10)
        for r in results:
            assert r.score <= 1.0, f"score {r.score} impossível — indica acúmulo indevido"

    def test_each_near_duplicate_keeps_its_own_score(self, db_with_near_duplicate_chunks):
        db, vector_store = db_with_near_duplicate_chunks
        results, info = vector_store.hybrid_search("duckdb", n_results=10)
        chunk_ids = {r.chunk_id for r in results}
        assert len(chunk_ids) == 4  # nenhum colapsou em outro por engano
