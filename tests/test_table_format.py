"""
tests/test_table_format.py — --format table: barra de cobertura segmentada

Funções puras testadas isoladamente (sem precisar de CLI/click/DB):
term_coverage, render_coverage_bar, relative_percent, circled_number,
origin_plain.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from total_recall.models import (
    circled_number,
    origin_plain,
    relative_percent,
    render_coverage_bar,
    term_coverage,
)


class TestTermCoverage:
    def test_literal_match(self):
        levels = term_coverage("contém duckdb no meio", ["duckdb"], [])
        assert levels == ["literal"]

    def test_absent(self):
        levels = term_coverage("texto sem relação nenhuma", ["duckdb"], [])
        assert levels == ["ausente"]

    def test_fuzzy_match_via_expansion(self):
        expansions = [{"original": "buscla", "expanded": ["busca", "buscar"]}]
        levels = term_coverage("vou buscar as sessões", ["buscla"], expansions)
        assert levels == ["fuzzy"]

    def test_literal_wins_over_fuzzy_when_both_present(self):
        """Se o termo literal aparece, não importa que uma expansão
        também apareça — o nível é literal, o mais forte dos dois."""
        expansions = [{"original": "duckdb", "expanded": ["duck"]}]
        levels = term_coverage("duckdb e duck no mesmo texto", ["duckdb"], expansions)
        assert levels == ["literal"]

    def test_multiple_terms_mixed_levels(self):
        expansions = [{"original": "buscla", "expanded": ["busca"]}]
        content = "um caminho vetorial separado, vou busca as sessões"
        levels = term_coverage(content, ["vetorial", "buscla", "ausente_total"], expansions)
        assert levels == ["literal", "fuzzy", "ausente"]

    def test_case_insensitive(self):
        levels = term_coverage("DuckDB em maiúsculas", ["duckdb"], [])
        assert levels == ["literal"]

    def test_empty_query_terms(self):
        assert term_coverage("qualquer coisa", [], []) == []

    def test_accent_insensitive_fuzzy_match(self):
        """Achado real: query "proxmox" expandiu fuzzy pra "proximo" (sem
        acento — mesma forma que o vocabulário do FTS5 guarda). Conteúdo
        real tinha "Próximo check: 09:50" (com acento) — comparação de
        string crua não batia, mesmo o FTS5 já tendo encontrado via
        tokenizer que remove acento por padrão. A barra mostrava "ausente"
        onde era, na verdade, um match fuzzy real."""
        expansions = [{"original": "proxmox", "expanded": ["proximo", "promo"]}]
        levels = term_coverage("Próximo check: 09:50", ["proxmox"], expansions)
        assert levels == ["fuzzy"]

    def test_accent_insensitive_literal_match(self):
        """O mesmo vale pro match literal — se a query tem acento e o
        conteúdo não (ou vice-versa), ainda conta como literal, porque o
        FTS5 já trata os dois como o mesmo token."""
        levels = term_coverage("uma analise completa", ["análise"], [])
        assert levels == ["literal"]


class TestRenderCoverageBar:
    def test_single_term_full_width(self):
        bar = render_coverage_bar(["literal"], total_width=10)
        assert bar == "[" + "█" * 10 + "]"

    def test_two_terms_split_width(self):
        bar = render_coverage_bar(["literal", "ausente"], total_width=10)
        assert bar == "[" + "█" * 5 + "|" + "░" * 5 + "]"

    def test_three_levels_all_distinct(self):
        bar = render_coverage_bar(["literal", "fuzzy", "ausente"], total_width=9)
        assert "█" in bar and "▒" in bar and "░" in bar
        assert bar.count("|") == 2

    def test_empty_levels(self):
        """Achado real: query sem termo válido (ex.: "a", 1 char) deixava
        a barra como "[]" vazio — parecia bug de exibição, não "nada pra
        mostrar aqui de propósito"."""
        assert render_coverage_bar([]) == "—"

    def test_many_terms_minimum_width_one(self):
        levels = ["literal"] * 15
        bar = render_coverage_bar(levels, total_width=10)
        # largura total menor que o número de termos — cada segmento
        # ainda tem no mínimo 1 char, não quebra
        assert bar.count("█") == 15


class TestRelativePercent:
    def test_top_result_is_100(self):
        assert relative_percent(0.85, 0.85) == 100

    def test_proportional(self):
        assert relative_percent(0.425, 0.85) == 50

    def test_zero_top_score_no_division_by_zero(self):
        assert relative_percent(0.5, 0.0) == 0

    def test_never_exceeds_100(self):
        # score maior que o "top" não deveria acontecer, mas não pode
        # gerar >100% se acontecer por algum arredondamento
        assert relative_percent(0.9, 0.85) == 100


class TestCircledNumber:
    def test_first_ten(self):
        assert circled_number(1) == "①"
        assert circled_number(2) == "②"
        assert circled_number(10) == "⑩"

    def test_beyond_twenty_falls_back(self):
        assert circled_number(21) == "(21)"


class TestOriginPlain:
    def test_known_origins(self):
        assert origin_plain("claude-code") == "CLAUDE-CODE"
        assert origin_plain("codex") == "CODEX"

    def test_unknown_origin_uppercased(self):
        assert origin_plain("outro") == "OUTRO"

    def test_no_brackets(self):
        assert "[" not in origin_plain("codex")
        assert "]" not in origin_plain("codex")
