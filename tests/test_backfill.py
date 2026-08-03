"""
tests/test_backfill.py — Backfill de embeddings sem apagar dados

Cobre: `Indexer.backfill_embeddings()` preenche chunks_vec e vira has_embedding
só para os chunks marcados has_embedding=0, sem tocar no restante do banco.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from total_recall.config import EMBEDDING_DIMENSIONS
from total_recall.database import Database
from total_recall.indexer import Indexer
from total_recall.vector_store import SQLiteVectorStore


@pytest.fixture
def fake_provider():
    provider = MagicMock()
    provider.model_name = "fake-model"
    provider.dimensions.return_value = EMBEDDING_DIMENSIONS
    provider.text_hash.side_effect = lambda text: f"hash-{text}"
    provider.embed_document.side_effect = lambda text: [0.1] * EMBEDDING_DIMENSIONS
    return provider


@pytest.fixture
def db_with_mixed_chunks(tmp_path, fake_provider):
    db = Database(db_path=tmp_path / "backfill.db")
    vector_store = SQLiteVectorStore(db, fake_provider)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, project_path, file_path, file_hash) "
            "VALUES ('s1', '/tmp/proj', '/tmp/proj/s1.jsonl', 'hash1')"
        )
    # chunk COM embedding (via add() normal)
    vector_store.add(
        session_id="s1", role="assistant", content="já tem embedding",
        timestamp=None, chunk_index=0, line_start=None, line_end=None,
        has_embedding=True, embed_model="fake-model", metadata=None,
    )
    # chunk SEM embedding (simula falha de indexação anterior)
    vector_store.add(
        session_id="s1", role="assistant", content="ficou sem embedding",
        timestamp=None, chunk_index=1, line_start=None, line_end=None,
        has_embedding=False, embed_model="none", metadata=None,
    )
    return db, vector_store


class TestBackfillEmbeddings:
    def test_fixes_only_missing_chunks(self, db_with_mixed_chunks, fake_provider):
        db, vector_store = db_with_mixed_chunks
        indexer = Indexer(db, vector_store, fake_provider, discovery=None)

        result = indexer.backfill_embeddings()

        assert result["chunks_checked"] == 1
        assert result["chunks_fixed"] == 1
        assert result["chunks_failed"] == 0

    def test_does_not_touch_chunk_that_already_had_embedding(self, db_with_mixed_chunks, fake_provider):
        db, vector_store = db_with_mixed_chunks
        indexer = Indexer(db, vector_store, fake_provider, discovery=None)
        indexer.backfill_embeddings()

        with db.connection() as conn:
            rows = conn.execute(
                "SELECT content, has_embedding FROM chunks ORDER BY id"
            ).fetchall()
        assert dict(rows[0])["has_embedding"] == 1  # já tinha, continua
        assert dict(rows[1])["has_embedding"] == 1  # foi corrigido

    def test_second_run_is_a_noop(self, db_with_mixed_chunks, fake_provider):
        db, vector_store = db_with_mixed_chunks
        indexer = Indexer(db, vector_store, fake_provider, discovery=None)
        indexer.backfill_embeddings()

        result = indexer.backfill_embeddings()
        assert result["chunks_checked"] == 0

    def test_no_rows_deleted_from_sessions_or_chunks(self, db_with_mixed_chunks, fake_provider):
        """Diferença central em relação a `index --full`: nada é apagado."""
        db, vector_store = db_with_mixed_chunks
        indexer = Indexer(db, vector_store, fake_provider, discovery=None)

        with db.connection() as conn:
            before = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

        indexer.backfill_embeddings()

        with db.connection() as conn:
            after = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert before == after == 2

    def test_returns_zeroed_report_without_provider(self, tmp_path):
        db = Database(db_path=tmp_path / "no_provider.db")
        vector_store = SQLiteVectorStore(db, None)
        indexer = Indexer(db, vector_store, None, discovery=None)

        result = indexer.backfill_embeddings()
        assert result == {"chunks_checked": 0, "chunks_fixed": 0, "chunks_failed": 0}
