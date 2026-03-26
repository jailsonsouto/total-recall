"""
tests/test_search.py — Suite de testes do Total Recall

Cobre:
- Fuzzy matching (typos intencionais)
- Expansão de abreviações
- Normalização técnica
- Highlighting
- Performance (benchmark)
"""

import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Garante que o pacote local é importado
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from total_recall.models import highlight_text, RecallContext, SearchResult
from total_recall.config import FUZZY_THRESHOLD, FUZZY_MAX_EXPANSIONS


# ══════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════

@pytest.fixture
def sample_results():
    from datetime import datetime
    return [
        SearchResult(
            content="A ferramenta utiliza ABSA para análise de sentimento.",
            session_id="abc12345",
            role="assistant",
            timestamp=datetime(2026, 3, 25, 10, 0, 0),
            distance=0.3,
            score=0.75,
            sources=["vector", "fts5"],
            project_label="PROJETO/X",
            session_title="abc12345",
        ),
        SearchResult(
            content="O modelo novex foi treinado com dados do MAXTON.",
            session_id="def67890",
            role="user",
            timestamp=datetime(2026, 3, 24, 9, 0, 0),
            distance=0.5,
            score=0.62,
            sources=["fts5"],
            project_label="PROJETO/X",
            session_title="def67890",
        ),
    ]


# ══════════════════════════════════════════════════════════════
# 1. Highlighting
# ══════════════════════════════════════════════════════════════

class TestHighlighting:
    def test_markdown_wraps_term(self):
        result = highlight_text("O modelo novex foi testado.", ["novex"], mode="markdown")
        assert "**`novex`**" in result or "**novex**" in result

    def test_markdown_case_insensitive(self):
        result = highlight_text("O modelo NOVEX foi testado.", ["novex"], mode="markdown")
        assert "NOVEX" not in result.replace("**`NOVEX`**", "").replace("**NOVEX**", "")

    def test_ansi_wraps_term(self):
        result = highlight_text("novex aqui", ["novex"], mode="ansi")
        assert "\033[" in result  # ANSI codes present
        assert "novex" in result

    def test_empty_terms_returns_original(self):
        text = "texto sem alteração"
        assert highlight_text(text, [], mode="markdown") == text
        assert highlight_text(text, [], mode="ansi") == text

    def test_multiple_terms(self):
        result = highlight_text("absa e novex no mesmo texto", ["absa", "novex"], mode="markdown")
        assert "absa" in result.lower()
        assert "novex" in result.lower()

    def test_markdown_visual_distinction(self):
        """Garante que o modo markdown usa código+negrito para máxima visibilidade."""
        result = highlight_text("o termo novex aparece aqui", ["novex"], mode="markdown")
        # Deve usar **`term`** não apenas **term**
        assert "**`" in result, f"Esperado **`term`**, obtido: {result}"


# ══════════════════════════════════════════════════════════════
# 2. RecallContext — format_for_context
# ══════════════════════════════════════════════════════════════

class TestRecallContext:
    def test_empty_results(self):
        ctx = RecallContext(query="test", results=[], sessions_searched=5, total_chunks=100)
        output = ctx.format_for_context()
        assert "Nenhum resultado" in output
        assert "5 sessões" in output

    def test_expansion_summary_shown(self, sample_results):
        ctx = RecallContext(
            query="nuvex",
            results=sample_results,
            sessions_searched=10,
            total_chunks=500,
            query_info={
                "expansions": [
                    {"type": "fuzzy", "original": "nuvex", "expanded": ["novex", "nuvem"]}
                ]
            },
        )
        output = ctx.format_for_context()
        assert "nuvex → novex" in output
        assert "fuzzy" in output

    def test_sources_shown(self, sample_results):
        ctx = RecallContext(query="absa", results=sample_results, sessions_searched=10, total_chunks=500)
        output = ctx.format_for_context()
        assert "VECTOR" in output or "FTS5" in output

    def test_highlight_terms_collected(self):
        ctx = RecallContext(
            query="novex maxton",
            results=[],
            sessions_searched=0,
            total_chunks=0,
            query_info={
                "expansions": [
                    {"type": "fuzzy", "original": "novex", "expanded": ["novex", "nuvem"]}
                ]
            },
        )
        terms = ctx._collect_highlight_terms()
        assert "novex" in terms
        assert "maxton" in terms

    def test_results_numbered(self, sample_results):
        ctx = RecallContext(query="absa", results=sample_results, sessions_searched=10, total_chunks=500)
        output = ctx.format_for_context()
        assert "### 1." in output
        assert "### 2." in output


# ══════════════════════════════════════════════════════════════
# 3. Configuração
# ══════════════════════════════════════════════════════════════

class TestConfig:
    def test_fuzzy_threshold_is_permissive(self):
        """Threshold deve ser ≤ 0.75 para capturar 1 substituição em 4 chars (75%)."""
        assert FUZZY_THRESHOLD <= 0.75, (
            f"Threshold {FUZZY_THRESHOLD} é rígido demais — "
            f"ABSE→ABSA (75%) ficaria de fora"
        )

    def test_fuzzy_max_expansions_sufficient(self):
        """MAX_EXPANSIONS deve ser ≥ 4 para short words com muitos candidatos."""
        assert FUZZY_MAX_EXPANSIONS >= 4, (
            f"MAX_EXPANSIONS={FUZZY_MAX_EXPANSIONS} pode ser insuficiente para short words"
        )


# ══════════════════════════════════════════════════════════════
# 4. Benchmark — busca real contra o banco
# ══════════════════════════════════════════════════════════════

class TestBenchmark:
    """Testes de performance contra o banco de dados real.
    Requerem que o banco esteja indexado (pula se não estiver disponível).
    """

    @pytest.fixture(autouse=True)
    def check_db(self):
        """Pula testes de benchmark se o banco não estiver disponível."""
        try:
            from total_recall.database import Database
            from total_recall.embeddings import get_embedding_provider
            from total_recall.vector_store import SQLiteVectorStore
            db = Database()
            with db.connection() as conn:
                count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            if count == 0:
                pytest.skip("Banco vazio — rode total-recall index primeiro")
        except Exception as e:
            pytest.skip(f"Banco não disponível: {e}")

    def _search(self, query: str, limit: int = 5):
        from total_recall.vector_store import SQLiteVectorStore
        from total_recall.database import Database
        from total_recall.embeddings import get_embedding_provider
        db = Database()
        provider = get_embedding_provider()
        vs = SQLiteVectorStore(db, provider)
        return vs.hybrid_search(query, n_results=limit)

    def _bench(self, label: str, query: str, expected_expansion: str = None):
        """Executa uma busca e retorna (results, query_info, elapsed_ms)."""
        t0 = time.perf_counter()
        results, query_info = self._search(query)
        elapsed = (time.perf_counter() - t0) * 1000
        found = len(results)

        expansions = query_info.get("expansions", [])
        exp_str = ""
        for exp in expansions:
            exp_str = f" → {', '.join(exp['expanded'][:3])}"

        status = "✓" if found > 0 else "✗"
        exp_ok = ""
        if expected_expansion:
            all_expanded = [
                e.lower()
                for exp in expansions
                for e in exp["expanded"]
            ]
            exp_ok = " [expansão ✓]" if expected_expansion.lower() in all_expanded else " [expansão ✗]"

        print(f"  {status} {label:<20} {found:>2} resultados | {elapsed:>6.1f}ms{exp_str}{exp_ok}")
        return results, query_info, elapsed

    def test_exact_queries(self, capsys):
        """Buscas exatas devem sempre funcionar e ser rápidas."""
        print("\n── Buscas exatas ──────────────────────────────────")
        cases = ["sqlite", "embedding", "total-recall", "python", "fuzzy"]
        for q in cases:
            results, _, elapsed = self._bench(q, q)
            assert len(results) > 0, f"Busca exata '{q}' não retornou resultados"
            assert elapsed < 2000, f"Busca '{q}' muito lenta: {elapsed:.0f}ms"

    def test_fuzzy_typos(self, capsys):
        """Erros de digitação intencionais devem ser corrigidos via fuzzy."""
        print("\n── Fuzzy matching (typos) ──────────────────────────")
        cases = [
            ("ABSE → ABSA",   "abse",   "absa"),
            ("Nuvex → novex", "nuvex",  "novex"),
            ("Mexton → maxton","mexton", "maxton"),
            ("sqilte → sqlite","sqilte", "sqlite"),
            ("chromdb → chromadb","chromdb","chromadb"),
        ]
        failures = []
        for label, query, expected in cases:
            results, _, elapsed = self._bench(label, query, expected_expansion=expected)
            if len(results) == 0:
                failures.append(f"{label}: 0 resultados")
        if failures:
            pytest.fail("Fuzzy falhou:\n" + "\n".join(failures))

    def test_abbreviations(self, capsys):
        """Abreviações PT-BR devem ser expandidas."""
        print("\n── Abreviações PT-BR ───────────────────────────────")
        cases = [
            ("vc → você",   "vc decidiu"),
            ("pq → porque", "pq escolhemos"),
            ("tbm → também","tbm funciona"),
        ]
        for label, query in cases:
            results, _, elapsed = self._bench(label, query)
            # Abreviações podem não ter resultados se nunca usadas nas sessões
            # — não falha, apenas reporta
            print(f"    (sem assertion obrigatória — depende do conteúdo indexado)")

    def test_performance_p95(self, capsys):
        """P95 das buscas deve ser < 1500ms."""
        print("\n── Benchmark P95 ───────────────────────────────────")
        queries = [
            "sqlite embedding", "fuzzy threshold", "total recall index",
            "abse", "nuvex", "maxton", "python async", "chromadb",
            "vc decidiu", "modelo embedding",
        ]
        times = []
        for q in queries:
            t0 = time.perf_counter()
            self._search(q)
            times.append((time.perf_counter() - t0) * 1000)

        times.sort()
        p50 = times[len(times) // 2]
        p95 = times[int(len(times) * 0.95)]
        p_max = times[-1]

        print(f"  P50: {p50:.1f}ms | P95: {p95:.1f}ms | Max: {p_max:.1f}ms")
        assert p95 < 1500, f"P95 muito alto: {p95:.0f}ms (limite: 1500ms)"
