"""
tests/test_crossover.py — Busca cruzada (read-only) com o total-recall-codex

Cobre:
- Database(read_only=True): erro claro se o banco não existe, transaction()
  bloqueada, e a conexão realmente não consegue escrever (erro do próprio
  sqlite, não só a checagem em Python).
- O caminho de escrita local não regrediu: PRAGMAs de WAL/foreign_keys
  continuam ativas (guard read_only não pode ter removido do ramo normal).
- recall_cross(): funde e ordena resultados de múltiplos engines por score.
- cli._build_sibling_engine(): None quando o banco irmão não existe.
- format_pointers(): origem aparece tanto no bloco citado na íntegra quanto
  nos ponteiros de 1 linha.
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from total_recall.database import Database
from total_recall.models import RecallContext, SearchResult, origin_label
from total_recall.recall_engine import recall_cross


# ══════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════

@pytest.fixture
def seeded_db_path(tmp_path):
    """Cria um banco válido (schema completo) num diretório temporário."""
    db_path = tmp_path / "seeded.db"
    Database(db_path=db_path)  # ramo de escrita: cria dir + schema
    return db_path


def _make_result(session_id, score, origin="claude-code"):
    return SearchResult(
        content=f"conteúdo de {session_id}",
        session_id=session_id,
        role="assistant",
        timestamp=datetime(2026, 8, 1, 10, 0, 0),
        distance=0.3,
        score=score,
        sources=["vector"],
        project_label="PROJETO/X",
        session_title=session_id,
        origin=origin,
    )


class _FakeEngine:
    """Stand-in para RecallEngine — recall_cross só precisa de .recall()."""

    def __init__(self, results, sessions_searched=1, total_chunks=1):
        self._results = results
        self._sessions_searched = sessions_searched
        self._total_chunks = total_chunks

    def recall(self, query, limit=5, session_id=None):
        return RecallContext(
            query=query,
            results=list(self._results),
            sessions_searched=self._sessions_searched,
            total_chunks=self._total_chunks,
            query_info={},
        )


# ══════════════════════════════════════════════════════════════
# 1. Database(read_only=True)
# ══════════════════════════════════════════════════════════════

class TestReadOnlyDatabase:
    def test_missing_path_raises_file_not_found(self, tmp_path):
        missing = tmp_path / "does-not-exist.db"
        with pytest.raises(FileNotFoundError):
            Database(db_path=missing, read_only=True)

    def test_read_only_never_creates_file(self, tmp_path):
        missing = tmp_path / "nested" / "does-not-exist.db"
        with pytest.raises(FileNotFoundError):
            Database(db_path=missing, read_only=True)
        assert not missing.parent.exists()

    def test_transaction_raises_runtime_error(self, seeded_db_path):
        db = Database(db_path=seeded_db_path, read_only=True)
        with pytest.raises(RuntimeError):
            with db.transaction():
                pass

    def test_write_actually_fails_at_sqlite_level(self, seeded_db_path):
        """A proteção não é só a checagem em Python — a conexão sqlite em
        si (uri mode=ro) recusa a escrita."""
        db = Database(db_path=seeded_db_path, read_only=True)
        with db.connection() as conn:
            with pytest.raises(sqlite3.OperationalError):
                conn.execute(
                    "INSERT INTO sessions "
                    "(session_id, project_path, file_path, file_hash) "
                    "VALUES ('x', 'y', 'z', 'h')"
                )

    def test_read_only_can_read(self, seeded_db_path):
        db = Database(db_path=seeded_db_path, read_only=True)
        with db.connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        assert count == 0


class TestWritePathUnaffected:
    """O guard read_only não pode ter removido as PRAGMAs do caminho normal
    de escrita — regressão real se `journal_mode`/`foreign_keys` sumirem."""

    def test_wal_and_foreign_keys_still_set_on_write_path(self, tmp_path):
        db = Database(db_path=tmp_path / "writer.db")
        with db.connection() as conn:
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert journal_mode.lower() == "wal"
        assert foreign_keys == 1

    def test_write_path_still_writable(self, tmp_path):
        db = Database(db_path=tmp_path / "writer2.db")
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO sessions "
                "(session_id, project_path, file_path, file_hash) "
                "VALUES ('x', 'y', 'z', 'h')"
            )
        with db.connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        assert count == 1


# ══════════════════════════════════════════════════════════════
# 2. recall_cross()
# ══════════════════════════════════════════════════════════════

class TestRecallCross:
    def test_merges_and_sorts_by_score(self):
        engines = {
            "claude-code": _FakeEngine([_make_result("a", 0.9), _make_result("b", 0.4)]),
            "codex": _FakeEngine([_make_result("c", 0.95), _make_result("d", 0.1)]),
        }
        ctx = recall_cross("query", engines, limit=10)
        scores = [r.score for r in ctx.results]
        assert scores == sorted(scores, reverse=True)
        assert ctx.results[0].session_id == "c"

    def test_tags_origin_per_engine(self):
        engines = {
            "claude-code": _FakeEngine([_make_result("a", 0.9, origin="claude-code")]),
            "codex": _FakeEngine([_make_result("b", 0.8, origin="claude-code")]),  # propositalmente errado
        }
        ctx = recall_cross("query", engines, limit=10)
        by_id = {r.session_id: r.origin for r in ctx.results}
        # recall_cross reatribui origin pela chave do dict, não confia no
        # valor que já veio no SearchResult
        assert by_id["a"] == "claude-code"
        assert by_id["b"] == "codex"

    def test_respects_limit_after_merge(self):
        engines = {
            "claude-code": _FakeEngine([_make_result(f"a{i}", 0.5) for i in range(5)]),
            "codex": _FakeEngine([_make_result(f"b{i}", 0.6) for i in range(5)]),
        }
        ctx = recall_cross("query", engines, limit=3)
        assert len(ctx.results) == 3

    def test_never_touches_disk_databases(self):
        """Fusão é só em memória — nenhum engine fake tem acesso a disco,
        e o teste passa sem qualquer arquivo .db envolvido."""
        engines = {"claude-code": _FakeEngine([_make_result("a", 0.5)])}
        ctx = recall_cross("query", engines, limit=5)
        assert len(ctx.results) == 1


# ══════════════════════════════════════════════════════════════
# 3. cli._build_sibling_engine()
# ══════════════════════════════════════════════════════════════

class TestBuildSiblingEngine:
    def test_returns_none_when_sibling_db_missing(self, tmp_path, monkeypatch):
        from total_recall import cli

        monkeypatch.setattr(cli, "SIBLING_DB_PATH", tmp_path / "nope.db")
        assert cli._build_sibling_engine(provider=None) is None

    def test_returns_engine_when_sibling_db_exists(self, seeded_db_path, monkeypatch):
        from total_recall import cli

        monkeypatch.setattr(cli, "SIBLING_DB_PATH", seeded_db_path)
        engine = cli._build_sibling_engine(provider=None)
        assert engine is not None
        assert engine.db.read_only is True


# ══════════════════════════════════════════════════════════════
# 4. format_pointers() mostra origem em ambos os blocos
# ══════════════════════════════════════════════════════════════

class TestPointersShowOrigin:
    def test_full_block_shows_origin(self):
        ctx = RecallContext(
            query="q",
            results=[_make_result("a", 0.9, origin="codex")],
            sessions_searched=1,
            total_chunks=1,
        )
        text = ctx.format_pointers(max_full_sessions=4)
        assert origin_label("codex") in text

    def test_rest_block_shows_origin(self):
        """Com max_full_sessions=1, o segundo resultado (sessão distinta)
        cai no bloco de ponteiros de 1 linha — que antes não mostrava
        origem nenhuma."""
        results = [
            _make_result("a", 0.9, origin="claude-code"),
            _make_result("b", 0.8, origin="codex"),
        ]
        ctx = RecallContext(
            query="q", results=results, sessions_searched=2, total_chunks=2,
        )
        text = ctx.format_pointers(max_full_sessions=1)
        assert "### Ponteiros" in text
        assert origin_label("codex") in text

    def test_mixed_origins_both_labeled(self):
        results = [
            _make_result("a", 0.9, origin="claude-code"),
            _make_result("b", 0.8, origin="codex"),
        ]
        ctx = RecallContext(
            query="q", results=results, sessions_searched=2, total_chunks=2,
        )
        text = ctx.format_for_context()
        assert origin_label("claude-code") in text
        assert origin_label("codex") in text
