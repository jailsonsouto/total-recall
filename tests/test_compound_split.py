"""
tests/test_compound_split.py — Split de palavra composta colada

Achado real: "ducklake"/"deltalake" (nomes de produto colados) não batem
com "duck lake"/"delta lake" (como o termo real aparece no corpus) nem via
FTS5 literal (tokens diferentes) nem via busca vetorial — verificado
empiricamente com embeddings reais (com e sem instrução de query), o termo
raro/novo não ancora bem no espaço de embedding mesmo com cosseno isolado
alto (0.97). Fix: split de palavra composta ataca a causa raiz
(tokenização), não depende de heurística de embedding.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from total_recall.database import Database
from total_recall.models import expansion_label
from total_recall.vector_store import SQLiteVectorStore


@pytest.fixture
def db_with_duck_lake_content(tmp_path):
    """Corpus com 'duck lake' (separado, como o termo real aparece) e
    ruído de palavras curtas que não deveriam formar splits válidos."""
    db = Database(db_path=tmp_path / "split.db")
    vector_store = SQLiteVectorStore(db, None)

    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, project_path, file_path, file_hash) "
            "VALUES ('s1', '/tmp', '/tmp/s1.jsonl', 'h1')"
        )

    contents = [
        "DuckDB/Duck Lake para consumidores analíticos, formato de tabela aberto",
        "Duck Lake é um formato de tabela mantido pela DuckDB Labs",
        "outra menção a duck lake no pipeline de dados",
        "conteúdo qualquer sem relação — apenas texto de preenchimento",
        "mais texto de preenchimento sem relação nenhuma com o assunto",
    ]
    for i, content in enumerate(contents):
        vector_store.add(
            session_id="s1", role="assistant", content=content,
            timestamp=None, chunk_index=i, line_start=None, line_end=None,
            has_embedding=False, embed_model="none", metadata=None,
        )
    return db, vector_store


class TestFindCompoundSplit:
    def test_finds_valid_split(self, db_with_duck_lake_content):
        db, vs = db_with_duck_lake_content
        with db.connection() as conn:
            result = vs._find_compound_split("ducklake", conn)
        assert result == "duck lake"

    def test_returns_none_for_short_token(self, db_with_duck_lake_content):
        db, vs = db_with_duck_lake_content
        with db.connection() as conn:
            result = vs._find_compound_split("abcde", conn)  # < 6 chars
        assert result is None

    def test_returns_none_when_no_valid_split_exists(self, db_with_duck_lake_content):
        db, vs = db_with_duck_lake_content
        with db.connection() as conn:
            result = vs._find_compound_split("xyzqwerty", conn)
        assert result is None

    def test_does_not_split_into_nonsense_fragments(self, db_with_duck_lake_content):
        """"ducklake" não deve virar "d"+"ucklake" ou "du"+"cklake" —
        nenhuma dessas metades existe no vocabulário real."""
        db, vs = db_with_duck_lake_content
        with db.connection() as conn:
            result = vs._find_compound_split("ducklake", conn)
        assert result != "d ucklake"
        assert result != "du cklake"


class TestBuildFtsQueryWithSplit:
    def test_query_includes_split_phrase(self, db_with_duck_lake_content):
        db, vs = db_with_duck_lake_content
        with db.connection() as conn:
            fts_query, expansions = vs._build_fts_query("ducklake", conn)
        assert '"duck lake"' in fts_query
        assert any(e["type"] in ("split", "fuzzy+split") for e in expansions)

    def test_end_to_end_keyword_search_finds_duck_lake_content(self, db_with_duck_lake_content):
        """Fim a fim: buscar "ducklake" (colado) precisa achar o conteúdo
        real que só existe como "duck lake" (separado)."""
        db, vs = db_with_duck_lake_content
        results, info = vs.keyword_search("ducklake", n_results=10)
        found = [r for r in results if "duck lake" in r.content.lower()]
        assert len(found) > 0, "split de palavra composta não achou o conteúdo real"


class TestSplitSurvivesTruncatedDisplay:
    def test_split_appears_first_so_it_survives_top3_truncation(self, db_with_duck_lake_content):
        """cli.py/models.py truncam a lista de expansão em [:3] pra exibição
        — se houvesse 5 variantes fuzzy antes do split, ele sumiria da
        vista mesmo tendo contribuído pro resultado. Split precisa vir
        primeiro na lista."""
        db, vs = db_with_duck_lake_content
        with db.connection() as conn:
            _, expansions = vs._build_fts_query("ducklake", conn)
        exp = next(e for e in expansions if e["original"] == "ducklake")
        assert exp["expanded"][0] == "duck lake"
        assert "duck lake" in exp["expanded"][:3]


class TestExpansionLabel:
    def test_known_types(self):
        assert expansion_label("fuzzy") == "fuzzy"
        assert expansion_label("abbreviation") == "abrev"
        assert expansion_label("split") == "composta"
        assert expansion_label("fuzzy+split") == "fuzzy+composta"

    def test_unknown_type_falls_back_to_itself_not_abrev(self):
        """Bug que este teste evita: um `else` genérico rotularia
        qualquer tipo novo como "abrev" por engano."""
        assert expansion_label("algum-tipo-novo") == "algum-tipo-novo"
        assert expansion_label("algum-tipo-novo") != "abrev"
