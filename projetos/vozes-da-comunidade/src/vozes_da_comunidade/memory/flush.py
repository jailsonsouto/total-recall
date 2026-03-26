"""
post_batch_flush — persiste ConsumerIntelligenceOutput no Warm Store (Agente 8).

Estratégia:
  1. Tenta importar MemoryManager da Memória Viva (caminho configurado em MEMORIA_VIVA_PATH).
  2. Se não disponível, salva em JSON local (data/vozes_cache/) como fallback.

A collection no Warm Store é "vozes_comunidade".
Cada chunk representa os indicadores de um (categoria, segmento) como texto pesquisável,
com metadata para filtros SQL posteriores.

O texto do chunk segue o padrão que o Agente 6 (Briefing Writer) espera na busca:
    "{categoria} {segmento}: dores={top_dores}, atributos={top_atributos}"
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from vozes_da_comunidade import config as cfg
from vozes_da_comunidade.indicators import ConsumerIntelligenceOutput

logger = logging.getLogger(__name__)

_COLLECTION = "vozes_comunidade"
_LOCAL_CACHE_DIR = Path("data/vozes_cache")


# ---------------------------------------------------------------------------
# Resultado do flush
# ---------------------------------------------------------------------------

@dataclass
class FlushResult:
    """Resumo do que foi persistido."""
    flushed: int = 0      # registros gravados no Warm Store
    cached: int = 0       # registros salvos em JSON local (fallback)
    failed: int = 0
    backend: str = "none"  # "warm_store" | "local_json"

    def summary(self) -> str:
        lines = [
            f"FlushResult [backend={self.backend}]",
            f"  ✓ gravados: {self.flushed}",
            f"  ✓ cache local: {self.cached}",
            f"  ✗ falhas: {self.failed}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Interface pública
# ---------------------------------------------------------------------------

def post_batch_flush(
    outputs: dict[tuple[str, str], ConsumerIntelligenceOutput],
) -> FlushResult:
    """
    Persiste todos os outputs do batch no Warm Store.

    Args:
        outputs: dict[(categoria, segmento)] → ConsumerIntelligenceOutput
                 saída direta do IndicatorCalculator.

    Returns:
        FlushResult com contagens de sucesso/falha.
    """
    store = _load_warm_store()
    result = FlushResult()

    for (categoria, segmento), output in outputs.items():
        try:
            if store is not None:
                _flush_to_warm_store(store, output)
                result.flushed += 1
                result.backend = "warm_store"
            else:
                _flush_to_local_cache(output)
                result.cached += 1
                result.backend = "local_json"
        except Exception as exc:
            logger.warning(
                "Falha ao persistir (%s, %s): %s", categoria, segmento, exc
            )
            result.failed += 1

    logger.info("\n%s", result.summary())
    return result


# ---------------------------------------------------------------------------
# Internos — Warm Store (Agente 8)
# ---------------------------------------------------------------------------

def _load_warm_store():
    """
    Tenta importar e instanciar o SQLiteVectorStore da Memória Viva.

    Retorna None se Memória Viva não estiver disponível — o fallback
    local JSON cobre esse caso.
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
        logger.info("Warm Store (Memória Viva) conectado.")
        return store
    except ImportError:
        logger.warning(
            "Memória Viva não disponível — usando fallback JSON local."
        )
        return None


def _flush_to_warm_store(store, output: ConsumerIntelligenceOutput) -> None:
    """
    Grava um ConsumerIntelligenceOutput como chunk no Warm Store.

    O texto do chunk é projetado para ser semanticamente buscável:
    reproduz as dores e atributos em linguagem natural para que a busca
    por "máscara hidratação enroladas" encontre o registro correto.
    """
    content = _build_chunk_text(output)
    metadata = {
        "categoria": output.categoria_produto,
        "segmento": output.segmento_dominante,
        "total_comentarios": output.total_comentarios_analisados,
        "briefing_relevance_score": output.briefing_relevance_score,
        "score_oportunidade": output.score_oportunidade,
        "n_dores": len(output.dores_principais),
        "n_atributos": len(output.atributos_conversao),
        "red_flags": output.red_flags,
        "source": "vozes_da_comunidade",
    }
    store.add(content=content, collection=_COLLECTION, metadata=metadata)
    logger.debug(
        "Chunk gravado: %s/%s (%d comentários)",
        output.categoria_produto,
        output.segmento_dominante,
        output.total_comentarios_analisados,
    )


def _build_chunk_text(output: ConsumerIntelligenceOutput) -> str:
    """
    Serializa ConsumerIntelligenceOutput em texto otimizado para embedding.

    Estrutura pensada para busca semântica:
    - começa com categoria + segmento (contexto de busca principal)
    - lista dores e atributos com aspecto + expressão de opinião
    - termina com red flags se houver
    """
    lines = [
        f"Categoria: {output.categoria_produto}",
        f"Segmento: {output.segmento_dominante}",
        f"Total analisado: {output.total_comentarios_analisados} comentários",
        "",
    ]

    if output.dores_principais:
        lines.append("DORES PRINCIPAIS (Prioridade Negativa):")
        for d in output.dores_principais[:5]:
            lines.append(
                f"  - {d.aspecto}: \"{d.opiniao_representativa}\" "
                f"(PN={d.score_pn:.3f}, {d.frequencia}x)"
            )
        lines.append("")

    if output.atributos_conversao:
        lines.append("ATRIBUTOS QUE CONVERTEM (Alavancagem Positiva):")
        for a in output.atributos_conversao[:5]:
            lines.append(
                f"  - {a.aspecto}: \"{a.opiniao_representativa}\" "
                f"(AP={a.score_ap:.3f}, {a.frequencia}x)"
            )
        lines.append("")

    if output.aspectos_controversos:
        lines.append("ASPECTOS CONTROVERSOS:")
        for c in output.aspectos_controversos[:3]:
            lines.append(
                f"  - {c.aspecto}: \"{c.opiniao_representativa}\" "
                f"(controvérsia={c.controversia:.2f})"
            )
        lines.append("")

    if output.red_flags:
        lines.append("RED FLAGS:")
        for flag in output.red_flags:
            lines.append(f"  ⚠ {flag}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internos — fallback JSON local
# ---------------------------------------------------------------------------

def _flush_to_local_cache(output: ConsumerIntelligenceOutput) -> None:
    """
    Salva ConsumerIntelligenceOutput como JSON local.

    Usado quando Memória Viva não está disponível.
    O Agente 6 pode ler diretamente deste diretório.
    """
    _LOCAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    filename = (
        f"{output.categoria_produto}_{output.segmento_dominante}.json"
        .replace("/", "_").replace(" ", "_").lower()
    )
    path = _LOCAL_CACHE_DIR / filename
    path.write_text(
        json.dumps(output.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.debug("Cache local gravado: %s", path)
