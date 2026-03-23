"""
Tipos de dados compartilhados entre os extratores ASTE.

ASTETriplet é o contrato de saída de qualquer extrator (BERTimbau ou SLM).
ExtractionContext é o contexto injetado a partir do schema V1 do comentário.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ASTETriplet:
    """
    Tripla ASTE extraída de um comentário.

    Campos obrigatórios preenchidos por ambos os extratores.
    Campos de span (offset) são preenchidos apenas pelo BERTimbauExtractor,
    pois dependem de BIO tagging token-level. O SLMExtractor deixa None.
    """

    aspecto: str
    """Expressão exata do texto que identifica o elemento avaliado."""

    opiniao: str
    """Expressão exata do texto que expressa o julgamento."""

    polaridade: str
    """POS | NEG | NEU | MIX"""

    confianca: float
    """Score de confiança do extrator (0.0 – 1.0)."""

    categoria_aspecto: str
    """
    Categoria do Codebook V3:
    PRODUTO | RESULTADO_EFICACIA | TEXTURA_CABELO | TEXTURA_PRODUTO |
    EMBALAGEM | APLICACAO | CUSTO | CRONOGRAMA_CAPILAR | PRESCRITOR |
    CABELO_TIPO | ATIVO_INGREDIENTE | CLAIM_EFICACIA |
    CUSTO_PERCEBIDO | ROTINA_CRONOGRAMA
    """

    frequencia: int = 1
    """Número de comentários com este padrão (calculado na fase de agregação)."""

    crescimento: float = 0.0
    """Variação trimestral de frequência em % (calculado na fase de agregação)."""

    span_aspecto: tuple[int, int] | None = None
    """(início, fim) do token de aspecto no texto. Apenas BERTimbauExtractor."""

    span_opiniao: tuple[int, int] | None = None
    """(início, fim) do token de opinião no texto. Apenas BERTimbauExtractor."""

    def to_dict(self) -> dict:
        return {
            "aspecto": self.aspecto,
            "opiniao": self.opiniao,
            "polaridade": self.polaridade,
            "confianca": self.confianca,
            "categoria_aspecto": self.categoria_aspecto,
            "frequencia": self.frequencia,
            "crescimento": self.crescimento,
            "span_aspecto": self.span_aspecto,
            "span_opiniao": self.span_opiniao,
        }


@dataclass
class ExtractionContext:
    """
    Contexto injetado no extrator a partir dos campos do schema V1.

    Esses campos já foram preenchidos durante a coleta/triagem com o Codebook V3.
    O extrator usa o contexto para melhorar a categorização de aspectos e
    interpretar corretamente o segmento da consumidora.
    """

    macro_theme: str = "indefinido"
    """
    Tema macro do vídeo — ex: 'reposicao_de_massa_reconstrucao_claims'.
    Mapeado de video.netnography_video_memo.macro_theme no schema V1.
    """

    segmento_hnr: str = "indefinido"
    """
    Segmento inferido: cacheadas | enroladas | henegatas | indefinido.
    Inferido via netnography.native_terms + cultural_markers no schema V1.
    """

    linguistic_signals: dict = field(default_factory=dict)
    """
    Sinais linguísticos do schema V1:
    has_negation, has_irony_signal, has_comparison_signal.
    """

    marca_primaria: str = ""
    """Marca principal do vídeo (video.brand_primary no schema V1)."""


def ctx_from_comment(comment: dict) -> ExtractionContext:
    """
    Constrói ExtractionContext a partir de um comentário no schema V1.

    Uso:
        ctx = ctx_from_comment(comment_dict)
        triplets = extractor.extract(comment["text_for_model"], ctx)
    """
    netnography = comment.get("netnography", {})
    native_terms = netnography.get("native_terms", [])
    cultural_markers = netnography.get("cultural_markers", [])

    segmento = _infer_hnr(native_terms, cultural_markers)

    return ExtractionContext(
        macro_theme=comment.get("macro_theme", "indefinido"),
        segmento_hnr=segmento,
        linguistic_signals=comment.get("linguistic_signals", {}),
        marca_primaria=comment.get("brand_primary", ""),
    )


# Vocabulário de segmentação HNR — alinhado com Codebook V3
_HNR_SIGNALS = {
    "cacheadas": {
        "native_terms": {"método curly", "gel ativador", "cachos", "low poo", "no poo",
                         "difusor", "ativador de cachos", "gelzinho"},
        "cultural_markers": {"cacheada", "crespa", "2c", "3a", "3b", "3c", "4a", "4b", "4c"},
    },
    "enroladas": {
        "native_terms": {"ondulado", "fininho", "umidade", "transição capilar",
                         "leveza", "volume"},
        "cultural_markers": {"enrolada", "ondulada", "1c", "2a", "2b"},
    },
    "henegatas": {
        "native_terms": {"progressiva", "alisamento", "relaxamento", "reconstrução",
                         "proteína", "botox capilar", "escova"},
        "cultural_markers": {"henê", "progressiva", "danificado", "química", "liso"},
    },
}


def _infer_hnr(native_terms: list[str], cultural_markers: list[str]) -> str:
    terms_lower = {t.lower() for t in native_terms}
    markers_lower = {m.lower() for m in cultural_markers}

    scores: dict[str, int] = {}
    for segmento, signals in _HNR_SIGNALS.items():
        score = len(terms_lower & signals["native_terms"]) * 2
        score += len(markers_lower & signals["cultural_markers"]) * 3
        if score > 0:
            scores[segmento] = score

    if not scores:
        return "indefinido"
    return max(scores, key=scores.__getitem__)
