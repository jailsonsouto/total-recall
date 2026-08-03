"""
tests/test_preview_window.py — Preview truncado centralizado no match

Bug real encontrado em produção: `total-recall search "duckdb analista"
--source both --format rich` retornou 5 chunks corretos (FTS5 bateu, score
combinado ok), mas nenhum preview mostrava "duckdb" ou "analista" — os
termos estavam presentes no chunk, só fora da janela fixa de 300 (rich) ou
120 (pointers) caracteres, que sempre começava em `content[0]`.

Validado empiricamente: um sub-agent Haiku, sem contexto prévio, rodou o
comando com o bug ainda presente e concluiu com confiança "isso é ruído,
a busca não funcionou" — errado. `preview_window()` existe pra isso não
acontecer mais.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from total_recall.models import (
    RecallContext,
    SearchResult,
    extract_query_terms,
    preview_window,
)
from datetime import datetime


# ══════════════════════════════════════════════════════════════
# extract_query_terms()
# ══════════════════════════════════════════════════════════════

class TestExtractQueryTerms:
    def test_splits_and_lowercases(self):
        assert extract_query_terms("DuckDB Analista") == ["duckdb", "analista"]

    def test_strips_punctuation(self):
        assert extract_query_terms("o que decidimos sobre duckdb?") == [
            "que", "decidimos", "sobre", "duckdb"
        ]

    def test_drops_single_char_tokens(self):
        assert extract_query_terms("a duckdb e o analista") == [
            "duckdb", "analista"
        ]

    def test_empty_query(self):
        assert extract_query_terms("") == []


# ══════════════════════════════════════════════════════════════
# preview_window() — janela centralizada
# ══════════════════════════════════════════════════════════════

class TestPreviewWindow:
    def test_short_content_returned_whole(self):
        content = "conteúdo curto com duckdb"
        result = preview_window(content, ["duckdb"], [], width=300)
        assert result == content
        assert "..." not in result

    def test_match_at_very_start_no_leading_ellipsis(self):
        content = "duckdb " + "x" * 500
        result = preview_window(content, ["duckdb"], [], width=300)
        assert result.startswith("duckdb")
        assert not result.startswith("...")

    def test_match_in_middle_gets_both_ellipses(self):
        content = "x" * 1000 + "duckdb" + "y" * 1000
        result = preview_window(content, ["duckdb"], [], width=300)
        assert "duckdb" in result
        assert result.startswith("...")
        assert result.endswith("...")

    def test_match_near_end_no_trailing_ellipsis(self):
        content = "x" * 1000 + "duckdb"
        result = preview_window(content, ["duckdb"], [], width=300)
        assert "duckdb" in result
        assert not result.endswith("...")

    def test_no_match_anywhere_falls_back_to_head(self):
        content = "x" * 1000
        result = preview_window(content, ["duckdb"], ["analista"], width=300)
        assert result.startswith("x" * 100)
        assert result.endswith("...")
        assert len(result.replace("...", "")) == 300

    def test_priority_term_wins_over_earlier_fallback_term(self):
        """A expansão fuzzy pode achar uma posição sem relação com a busca
        real — priority_terms (a query literal) deve vencer mesmo se o
        fallback_term aparecer antes no texto."""
        content = "when " + "x" * 500 + "duckdb" + "y" * 500
        # "when" (fallback, aparece logo no início) vs "duckdb" (priority, no meio)
        result = preview_window(content, ["duckdb"], ["when"], width=300)
        assert "duckdb" in result
        assert "when" not in result  # não centralizou na palavra comum

    def test_falls_back_to_fallback_terms_when_priority_absent(self):
        content = "x" * 1000 + "wrenai" + "y" * 1000
        # query literal "wren" não aparece de verdade no texto (foi expandido
        # via fuzzy pra "wrenai") — preview_window deve usar o fallback
        result = preview_window(content, ["wren"], ["wrenai"], width=300)
        assert "wrenai" in result

    def test_fallback_extends_window_when_priority_already_anchored(self):
        """Achado real ("buscla vetorial"): "vetorial" (priority, literal) e
        "buscar" (fallback, fuzzy de "buscla") no mesmo chunk — antes do fix,
        o fallback era ignorado assim que "vetorial" sozinho já ancorava a
        janela, escondendo "buscar" mesmo estando por perto."""
        content = (
            "x" * 100
            + "vou buscar as sessões indexadas "
            + "y" * 50
            + "um caminho vetorial separado"
            + "z" * 100
        )
        result = preview_window(content, ["vetorial"], ["buscar"], width=300)
        assert "vetorial" in result
        assert "buscar" in result

    def test_fallback_does_not_override_priority_when_far_and_unhelpful(self):
        """Fallback só ESTENDE uma janela já ancorada — se estender ultrapassar
        max_width, cai de volta pro comportamento de só um termo (o já
        existente teste de "termos longe demais"), sem quebrar."""
        content = "x" * 100 + "vetorial" + "y" * 5000 + "buscar" + "z" * 100
        result = preview_window(content, ["vetorial"], ["buscar"], width=300)
        assert "vetorial" in result
        # "buscar" pode ou não aparecer — está longe demais pra caber; o
        # importante é não quebrar e continuar mostrando "vetorial" com clareza

    def test_two_terms_close_together_both_appear(self):
        """Achado pelo Haiku após o primeiro fix: um chunk com "duckdb" e
        "analista" a poucos chars de distância é um match completo, mas
        centralizar só no primeiro escondia o segundo."""
        content = (
            "x" * 400
            + "duckdb calcula métricas para o "
            + "analista revisar depois"
            + "y" * 400
        )
        result = preview_window(content, ["duckdb", "analista"], [], width=300)
        assert "duckdb" in result.lower()
        assert "analista" in result.lower()

    def test_two_terms_far_apart_falls_back_to_first(self):
        """Quando os termos estão longe demais pra caber numa janela
        razoável, mostra o primeiro com clareza em vez de uma janela gigante
        ou dois termos raspando nas bordas."""
        content = "x" * 400 + "duckdb" + "y" * 5000 + "analista" + "z" * 400
        result = preview_window(content, ["duckdb", "analista"], [], width=300)
        assert "duckdb" in result.lower()
        # não precisa conter "analista" — está longe demais pra caber

    def test_custom_max_width_respected(self):
        content = "x" * 400 + "duckdb" + "y" * 300 + "analista" + "z" * 400
        # span (~306) cabe no max_width=350 default (width*2=600)? cabe.
        # com max_width=350, span+width(300)=606 > 350 → não expande
        result = preview_window(content, ["duckdb", "analista"], [], width=300, max_width=350)
        assert len(result) <= 350 + 6

    def test_regex_special_chars_in_terms_do_not_crash(self):
        content = "x" * 200 + "session_id (config)" + "y" * 200
        result = preview_window(content, ["session_id (config)"], [], width=100)
        assert "session_id (config)" in result

    def test_case_insensitive_match(self):
        content = "x" * 500 + "DuckDB" + "y" * 500
        result = preview_window(content, ["duckdb"], [], width=200)
        assert "DuckDB" in result

    def test_width_120_used_by_pointers_format(self):
        content = "x" * 500 + "analista" + "y" * 500
        result = preview_window(content, ["analista"], [], width=120)
        assert "analista" in result
        # janela não deve extrapolar muito o width pedido (+ elipses)
        assert len(result) <= 120 + 6


# ══════════════════════════════════════════════════════════════
# Regressão: reprodução exata do bug real ("duckdb analista")
# ══════════════════════════════════════════════════════════════

class TestDuckdbAnalistaRegression:
    """Chunk real tem até MAX_CHUNK_CHARS=1500. O bug: content[:300] não
    necessariamente contém o termo buscado num chunk desse tamanho."""

    def _build_realistic_chunk(self) -> str:
        filler_before = (
            "hot/adapter seriam servidos por adesão incremental, sem "
            "reescrita, com a Garimpeira como cliente-piloto por já falar "
            "HTTP. Estima código-cola total de ~900 LOC nas fases 1-2. "
        ) * 3  # empurra o match pra além de 300 chars
        match = "| **DuckDB** | Profiling/cobertura/deriva rápidos | MIT |"
        filler_after = "resto do chunk sem relação direta com a query. " * 5
        return filler_before + match + filler_after

    def test_old_head_truncation_would_have_missed_it(self):
        """Documenta o bug original pra não reintroduzir por engano: os
        primeiros 300 chars puros (sem centralização) não contêm o termo."""
        content = self._build_realistic_chunk()
        assert len(content) > 300
        old_buggy_preview = content[:300]
        assert "duckdb" not in old_buggy_preview.lower()

    def test_new_preview_window_contains_the_term(self):
        content = self._build_realistic_chunk()
        result = preview_window(content, ["duckdb", "analista"], [], width=300)
        assert "duckdb" in result.lower()

    def test_both_terms_present_but_apart_regression(self):
        """Reprodução exata do caso real (sessão 019fc27d, resultado [4]):
        "Pergunta do analista" e "DuckDB: calcula métricas" no mesmo bloco
        mermaid, separados por ~150 chars de outras linhas do diagrama —
        um match completo que o Haiku (pós primeiro fix) reportou como
        "incompleto" porque só um termo cabia na janela de 300 chars."""
        content = (
            "```mermaid\nflowchart TD\n"
            '    A["Pergunta do analista"] --> B["DeepSeek: planeja a investigação"]\n'
            '    B <--> C["Ferramentas locais read-only"]\n'
            '    C --> C1["Busca Inteligente: encontra vozes"]\n'
            '    C --> C2["DuckDB: calcula métricas e universos"]\n'
            '    C --> C3["Novelo: resolve sentidos e ambiguidades"]\n'
            '    C --> C4["Grafo conversacional: expande pai e replies"]\n'
            '    B --> D["EvidencePacket congelado e auditável"]\n'
            '    D --> E["DeepSeek: redige resposta humana"]\n'
            "```\n"
        )
        result = preview_window(content, ["duckdb", "analista"], [], width=300)
        assert "analista" in result.lower()
        assert "duckdb" in result.lower()
        assert "duckdb" in result.lower()

    def test_format_pointers_rest_block_shows_the_term(self):
        """Fim a fim: RecallContext.format_pointers() (bloco de ponteiros
        de 1 linha, width=120) precisa mostrar o termo — não só a função
        pura preview_window()."""
        content = self._build_realistic_chunk()
        results = [
            SearchResult(
                content=content, session_id="a", role="assistant",
                timestamp=datetime(2026, 8, 3), distance=0.3, score=0.25,
                sources=["vector", "fts5"], project_label="PROJETO/X",
                session_title="a",
            ),
            SearchResult(
                content="segunda sessão, força o primeiro resultado pro "
                        "bloco de ponteiros em vez do bloco citado na íntegra",
                session_id="b", role="assistant",
                timestamp=datetime(2026, 8, 3), distance=0.3, score=0.20,
                sources=["fts5"], project_label="PROJETO/Y", session_title="b",
            ),
        ]
        ctx = RecallContext(
            query="duckdb analista", results=results,
            sessions_searched=2, total_chunks=2,
        )
        text = ctx.format_pointers(max_full_sessions=0)
        assert "duckdb" in text.lower()


# ══════════════════════════════════════════════════════════════
# Cenários adicionais de estresse — legibilidade pra sub-agente fraco
# ══════════════════════════════════════════════════════════════

class TestWeakAgentLegibility:
    """Não testam preview_window diretamente — testam se o output do
    RecallContext continua inequívoco o suficiente pra um modelo fraco
    (Haiku) não precisar inferir nada."""

    def test_zero_results_message_is_unambiguous(self):
        ctx = RecallContext(query="algo inexistente", results=[],
                            sessions_searched=10, total_chunks=500)
        text = ctx.format_for_context()
        assert "Nenhum resultado encontrado" in text
        assert "algo inexistente" in text

    def test_mixed_origin_pointers_never_ambiguous_about_source(self):
        """Todo resultado, local ou remoto, carrega o rótulo de origem —
        um leitor (humano ou modelo) não precisa inferir por ausência de
        marca, que é exatamente o tipo de inferência que um modelo fraco
        erra."""
        content = "x" * 500
        results = [
            SearchResult(
                content=content, session_id="a", role="assistant",
                timestamp=datetime(2026, 8, 3), distance=0.3, score=0.9,
                sources=["vector"], project_label="P1", session_title="a",
                origin="claude-code",
            ),
            SearchResult(
                content=content, session_id="b", role="assistant",
                timestamp=datetime(2026, 8, 3), distance=0.3, score=0.8,
                sources=["vector"], project_label="P2", session_title="b",
                origin="codex",
            ),
        ]
        ctx = RecallContext(query="q", results=results,
                            sessions_searched=2, total_chunks=2)
        text = ctx.format_pointers(max_full_sessions=0)
        assert "[CLAUDE-CODE]" in text
        assert "[CODEX]" in text
