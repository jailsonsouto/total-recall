"""
formatter.py — Síntese da seção "INTELIGÊNCIA DE CONSUMIDOR" via Claude Haiku.

Fluxo:
  1. Busca padrões relevantes no Warm Store (Agente 8) para a query do briefing.
  2. Filtra por briefing_relevance_score ≥ threshold.
  3. Envia os padrões ao Claude Haiku com prompt estruturado.
  4. Retorna a seção formatada pronta para injeção no Agente 6 (Briefing Writer).

Se o Warm Store não estiver disponível, usa os dados passados diretamente
(ex: resultado do batch recém-executado).
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass

import anthropic

from vozes_da_comunidade import config as cfg
from vozes_da_comunidade.indicators import ConsumerIntelligenceOutput

logger = logging.getLogger(__name__)

_COLLECTION = "vozes_comunidade"
_SECTION_HEADER = "## INTELIGÊNCIA DE CONSUMIDOR (Vozes da Comunidade)"


# ---------------------------------------------------------------------------
# Estruturas de saída
# ---------------------------------------------------------------------------

@dataclass
class SynthesisResult:
    """Resultado da síntese — seção pronta para o briefing."""
    section_text: str           # texto formatado para injeção no briefing
    sources_used: int = 0       # quantos padrões do Warm Store foram usados
    model_used: str = ""
    tokens_in: int = 0
    tokens_out: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.section_text.strip()


# ---------------------------------------------------------------------------
# Interface pública
# ---------------------------------------------------------------------------

def synthesize(
    query: str,
    *,
    direct_outputs: dict[tuple[str, str], ConsumerIntelligenceOutput] | None = None,
    n_results: int = 5,
) -> SynthesisResult:
    """
    Gera a seção "INTELIGÊNCIA DE CONSUMIDOR" para um briefing.

    Args:
        query: texto de busca (ex: "máscara de reconstrução cacheadas").
        direct_outputs: se fornecido, usa esses outputs diretamente
                        (sem buscar no Warm Store). Útil logo após um batch.
        n_results: máximo de padrões a buscar no Warm Store.

    Returns:
        SynthesisResult com a seção formatada.
    """
    # Coleta padrões como textos prontos para o prompt
    pattern_texts = _collect_pattern_texts(query, direct_outputs, n_results)

    if not pattern_texts:
        logger.warning("Nenhum padrão encontrado para a query: %s", query)
        return SynthesisResult(
            section_text=(
                f"{_SECTION_HEADER}\n\n"
                "_Nenhum dado disponível para este segmento no corpus atual._"
            )
        )

    # Síntese via Claude Haiku
    return _synthesize_with_haiku(query, pattern_texts)


# ---------------------------------------------------------------------------
# Coleta de padrões
# ---------------------------------------------------------------------------

def _collect_pattern_texts(
    query: str,
    direct_outputs: dict[tuple[str, str], ConsumerIntelligenceOutput] | None,
    n_results: int,
) -> list[str]:
    """
    Retorna lista de textos de padrões prontos para injeção no prompt.

    Prioridade:
      1. direct_outputs (passados diretamente — sem latência)
      2. Warm Store via busca semântica (dados históricos do corpus)
    """
    if direct_outputs:
        threshold = cfg.BRIEFING_RELEVANCE_THRESHOLD
        relevant = sorted(
            [out for out in direct_outputs.values()
             if out.briefing_relevance_score >= threshold],
            key=lambda x: x.score_oportunidade,
            reverse=True,
        )[:n_results]
        return [_output_to_text(out) for out in relevant]

    return _search_warm_store(query, n_results)


def _search_warm_store(query: str, n_results: int) -> list[str]:
    """
    Busca padrões no Warm Store da Memória Viva via hybrid_search.

    Retorna lista de chunk texts prontos para injeção no prompt.
    Se o Warm Store não estiver disponível, retorna lista vazia.
    """
    memoria_path = cfg.MEMORIA_VIVA_PATH
    if memoria_path and memoria_path not in sys.path:
        sys.path.insert(0, memoria_path)

    try:
        from memoria_viva.database import Database          # type: ignore
        from memoria_viva.embeddings import get_embedding_provider  # type: ignore
        from memoria_viva.vector_store import SQLiteVectorStore     # type: ignore

        db = Database()
        embed = get_embedding_provider()
        store = SQLiteVectorStore(db, embed)

        results = store.hybrid_search(
            query=query,
            collection=_COLLECTION,
            n_results=n_results,
        )

        # Filtra por briefing_relevance_score nos metadados
        threshold = cfg.BRIEFING_RELEVANCE_THRESHOLD
        return [
            r.content for r in results
            if r.metadata.get("briefing_relevance_score", 0) >= threshold
        ]

    except ImportError:
        logger.warning("Warm Store não disponível para síntese.")
        return []


# ---------------------------------------------------------------------------
# Síntese via Claude Haiku
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
Você é um analista de inteligência de consumidor especializado em beleza capilar.
Sua tarefa é sintetizar dados de comentários do TikTok em insights acionáveis
para o time de inovação de produtos da Embelleze/Novex.

Escreva em português. Seja direto, preciso e baseado nos dados fornecidos.
Não invente informações — use apenas o que está nos dados.
"""

_USER_TEMPLATE = """\
Query do briefing: "{query}"

Dados do corpus (comentários TikTok analisados):

{patterns_text}

---

Gere a seção "INTELIGÊNCIA DE CONSUMIDOR" para este briefing.
A seção deve conter:

1. **Síntese do Consumidor** (2–3 frases): perfil do segmento e contexto geral
2. **Dores Principais** (lista com bullet points, máximo 5):
   - aspecto: expressão real da consumidora (frequência)
3. **Atributos que Convertem** (lista com bullet points, máximo 5):
   - aspecto: expressão real da consumidora (frequência)
4. **Aspectos Controversos** (se houver, máximo 3): aspectos com opinião dividida
5. **Red Flags** (se houver): alertas para formulação/claim
6. **Score de Oportunidade**: X/10 — com frase de interpretação

Formato: markdown. Comece diretamente com o conteúdo (sem repetir o título da seção).
"""


def _synthesize_with_haiku(
    query: str,
    pattern_texts: list[str],
) -> SynthesisResult:
    """Chama Claude Haiku e retorna a seção formatada."""
    client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)

    patterns_text = "\n\n".join(
        f"--- Padrão {i} ---\n{t}" for i, t in enumerate(pattern_texts, 1)
    )
    user_message = _USER_TEMPLATE.format(
        query=query,
        patterns_text=patterns_text,
    )

    logger.debug("Enviando %d padrões para síntese Haiku.", len(pattern_texts))

    response = client.messages.create(
        model=cfg.SYNTHESIS_MODEL,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    section_body = response.content[0].text
    section_text = f"{_SECTION_HEADER}\n\n{section_body}"

    return SynthesisResult(
        section_text=section_text,
        sources_used=len(pattern_texts),
        model_used=cfg.SYNTHESIS_MODEL,
        tokens_in=response.usage.input_tokens,
        tokens_out=response.usage.output_tokens,
    )


def _output_to_text(output: ConsumerIntelligenceOutput) -> str:
    """Serializa ConsumerIntelligenceOutput como texto para o prompt."""
    lines = [
        f"Categoria: {output.categoria_produto}",
        f"Segmento: {output.segmento_dominante}",
        f"Total analisado: {output.total_comentarios_analisados} comentários",
        f"Score de Oportunidade: {output.score_oportunidade}/10",
        "",
    ]

    if output.dores_principais:
        lines.append("DORES PRINCIPAIS:")
        for d in output.dores_principais[:5]:
            lines.append(
                f"  - {d.aspecto}: \"{d.opiniao_representativa}\" "
                f"(PN={d.score_pn:.3f}, {d.frequencia}x)"
            )

    if output.atributos_conversao:
        lines.append("ATRIBUTOS QUE CONVERTEM:")
        for a in output.atributos_conversao[:5]:
            lines.append(
                f"  - {a.aspecto}: \"{a.opiniao_representativa}\" "
                f"(AP={a.score_ap:.3f}, {a.frequencia}x)"
            )

    if output.aspectos_controversos:
        lines.append("CONTROVERSOS:")
        for c in output.aspectos_controversos[:3]:
            lines.append(
                f"  - {c.aspecto}: \"{c.opiniao_representativa}\" "
                f"(controvérsia={c.controversia:.2f})"
            )

    if output.red_flags:
        lines.append("RED FLAGS:")
        for flag in output.red_flags:
            lines.append(f"  ⚠ {flag}")

    return "\n".join(lines)
