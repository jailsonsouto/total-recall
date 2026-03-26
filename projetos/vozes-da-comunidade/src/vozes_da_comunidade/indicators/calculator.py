"""
Calculador de indicadores PN / AP / Controvérsia / Crescimento.

Recebe as triplas extraídas pelo ASTEExtractor e agrega por (categoria, segmento HNR),
produzindo o ConsumerIntelligenceOutput que vai para o Warm Store.

Definições (alinhadas com o TCC / Codebook V3):
  PN  = Prioridade Negativa:  quais dores a comunidade mais sente
  AP  = Alavancagem Positiva: quais atributos mais convertem
  Controvérsia: aspectos com opinião dividida (nem claramente POS nem NEG)
  Crescimento:  aspectos com aumento de frequência no corpus recente

Entrada: list[tuple[dict, list[ASTETriplet]]]  ← saída do BatchPipeline
Saída:   dict[(categoria, segmento)] → ConsumerIntelligenceOutput
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from vozes_da_comunidade.types import ASTETriplet


# ---------------------------------------------------------------------------
# Estruturas de saída
# ---------------------------------------------------------------------------

@dataclass
class IndicatorTriplet:
    """Tripla agregada com indicadores calculados."""
    aspecto: str
    opiniao_representativa: str   # expressão mais frequente para este aspecto
    polaridade_dominante: str     # POS | NEG | NEU | MIX
    categoria_aspecto: str

    frequencia: int = 0           # nº de comentários com este padrão
    confianca_media: float = 0.0  # média das confianças do extrator
    score_pn: float = 0.0         # Prioridade Negativa (0–1)
    score_ap: float = 0.0         # Alavancagem Positiva (0–1)
    controversia: float = 0.0     # 0 = consenso, 1 = totalmente dividido
    crescimento: float = 0.0      # variação de frequência (futuro)

    # contagens internas de polaridade
    _count_pos: int = field(default=0, repr=False)
    _count_neg: int = field(default=0, repr=False)
    _count_neu: int = field(default=0, repr=False)

    def to_aste_triplet(self) -> ASTETriplet:
        return ASTETriplet(
            aspecto=self.aspecto,
            opiniao=self.opiniao_representativa,
            polaridade=self.polaridade_dominante,
            confianca=self.confianca_media,
            categoria_aspecto=self.categoria_aspecto,
            frequencia=self.frequencia,
            crescimento=self.crescimento,
        )


@dataclass
class ConsumerIntelligenceOutput:
    """
    Output completo do Vozes da Comunidade para um (categoria, segmento).
    Persistido no Warm Store e injetado no briefing.
    """
    categoria_produto: str
    segmento_dominante: str           # cacheadas | enroladas | henegatas | indefinido
    segmento_score: float             # proporção do corpus neste segmento
    total_comentarios_analisados: int
    briefing_relevance_score: float   # calculado com base na cobertura

    # Indicadores ordenados por score
    dores_principais: list[IndicatorTriplet] = field(default_factory=list)
    atributos_conversao: list[IndicatorTriplet] = field(default_factory=list)
    aspectos_controversos: list[IndicatorTriplet] = field(default_factory=list)
    tendencias_emergentes: list[IndicatorTriplet] = field(default_factory=list)

    red_flags: list[str] = field(default_factory=list)
    score_oportunidade: float = 0.0   # 0–10

    def to_dict(self) -> dict[str, Any]:
        return {
            "categoria_produto": self.categoria_produto,
            "segmento_dominante": self.segmento_dominante,
            "segmento_score": self.segmento_score,
            "total_comentarios": self.total_comentarios_analisados,
            "briefing_relevance_score": self.briefing_relevance_score,
            "dores_principais": [self._triplet_dict(t) for t in self.dores_principais],
            "atributos_conversao": [self._triplet_dict(t) for t in self.atributos_conversao],
            "aspectos_controversos": [self._triplet_dict(t) for t in self.aspectos_controversos],
            "red_flags": self.red_flags,
            "score_oportunidade": self.score_oportunidade,
        }

    @staticmethod
    def _triplet_dict(t: IndicatorTriplet) -> dict:
        return {
            "aspecto": t.aspecto,
            "opiniao": t.opiniao_representativa,
            "polaridade": t.polaridade_dominante,
            "frequencia": t.frequencia,
            "score_pn": round(t.score_pn, 3),
            "score_ap": round(t.score_ap, 3),
            "controversia": round(t.controversia, 3),
        }


# ---------------------------------------------------------------------------
# Calculador
# ---------------------------------------------------------------------------

# Thresholds para classificação
_PN_THRESHOLD = 0.35       # score PN acima disso → dor principal
_AP_THRESHOLD = 0.35       # score AP acima disso → atributo de conversão
_CONTROVERSIA_THRESHOLD = 0.40   # equilíbrio POS/NEG acima disso → controverso
_TOP_N = 10                # máximo de itens por categoria de indicador


class IndicatorCalculator:
    """
    Calcula PN, AP, Controvérsia e Crescimento a partir de triplas ASTE.

    Uso:
        calculator = IndicatorCalculator()
        outputs = calculator.calculate(batch_result.triplets_by_comment)
        # outputs: dict[(categoria, segmento)] → ConsumerIntelligenceOutput
    """

    def calculate(
        self,
        triplets_by_comment: list[tuple[dict, list[ASTETriplet]]],
    ) -> dict[tuple[str, str], ConsumerIntelligenceOutput]:
        """
        Agrega triplas por (categoria, segmento) e calcula indicadores.

        Args:
            triplets_by_comment: lista de (comentário_dict, [ASTETriplet])
                                 saída direta do BatchPipeline.

        Returns:
            Dicionário indexado por (categoria_produto, segmento_hnr).
        """
        # Agrupa triplas por (categoria, segmento)
        grouped = self._group_by_category_segment(triplets_by_comment)

        outputs: dict[tuple[str, str], ConsumerIntelligenceOutput] = {}
        for (categoria, segmento), data in grouped.items():
            outputs[(categoria, segmento)] = self._compute(
                categoria, segmento, data
            )
        return outputs

    # ------------------------------------------------------------------
    # Agrupamento
    # ------------------------------------------------------------------

    def _group_by_category_segment(
        self,
        triplets_by_comment: list[tuple[dict, list[ASTETriplet]]],
    ) -> dict[tuple[str, str], dict]:
        """
        Agrupa por (categoria, segmento) e indexa triplas por aspecto.

        Estrutura interna por grupo:
          {
            "total_comments": int,
            "aspects": {
              aspecto_str: {
                "triplets": [ASTETriplet, ...],
                "opinions": [str, ...],
                "count_pos": int, "count_neg": int, "count_neu": int,
                "categoria_aspecto": str,
              }
            }
          }
        """
        grouped: dict[tuple[str, str], dict] = defaultdict(lambda: {
            "total_comments": 0,
            "aspects": defaultdict(lambda: {
                "triplets": [],
                "opinions": [],
                "count_pos": 0,
                "count_neg": 0,
                "count_neu": 0,
                "count_mix": 0,
                "categoria_aspecto": "PRODUTO",
                "confiancas": [],
            }),
        })

        for comment, triplets in triplets_by_comment:
            if not triplets:
                continue

            # Inferir categoria do vídeo / segmento do comentário
            categoria = self._infer_categoria(comment)
            segmento = self._infer_segmento(comment)

            key = (categoria, segmento)
            grouped[key]["total_comments"] += 1

            for triplet in triplets:
                asp = triplet.aspecto.lower().strip()
                bucket = grouped[key]["aspects"][asp]
                bucket["triplets"].append(triplet)
                bucket["opinions"].append(triplet.opiniao)
                bucket["categoria_aspecto"] = triplet.categoria_aspecto
                bucket["confiancas"].append(triplet.confianca)

                pol = triplet.polaridade
                if pol == "POS":
                    bucket["count_pos"] += 1
                elif pol == "NEG":
                    bucket["count_neg"] += 1
                elif pol == "MIX":
                    bucket["count_mix"] += 1
                else:
                    bucket["count_neu"] += 1

        return dict(grouped)

    # ------------------------------------------------------------------
    # Cálculo de indicadores
    # ------------------------------------------------------------------

    def _compute(
        self,
        categoria: str,
        segmento: str,
        data: dict,
    ) -> ConsumerIntelligenceOutput:
        total_comments = data["total_comments"]
        aspects = data["aspects"]

        # Calcula IndicatorTriplet para cada aspecto
        indicators: list[IndicatorTriplet] = []
        for aspecto, bucket in aspects.items():
            ind = self._compute_aspect(aspecto, bucket, total_comments)
            indicators.append(ind)

        # Classifica em categorias
        dores = sorted(
            [i for i in indicators if i.score_pn >= _PN_THRESHOLD],
            key=lambda x: x.score_pn, reverse=True,
        )[:_TOP_N]

        atributos = sorted(
            [i for i in indicators if i.score_ap >= _AP_THRESHOLD],
            key=lambda x: x.score_ap, reverse=True,
        )[:_TOP_N]

        controversos = sorted(
            [i for i in indicators if i.controversia >= _CONTROVERSIA_THRESHOLD],
            key=lambda x: x.controversia, reverse=True,
        )[:5]

        # Red flags: NEG alta + aspecto em categorias de formulação
        red_flags = self._extract_red_flags(dores)

        # Score de oportunidade: AP alta - PN alta + frequência relativa
        score_op = self._score_oportunidade(indicators, total_comments)

        # Relevância do briefing: proporção do corpus coberto
        relevance = min(1.0, total_comments / 100)  # baseline: 100 comentários = relevância plena

        return ConsumerIntelligenceOutput(
            categoria_produto=categoria,
            segmento_dominante=segmento,
            segmento_score=1.0,   # em batch único, score = 1.0 (sem comparação entre segmentos ainda)
            total_comentarios_analisados=total_comments,
            briefing_relevance_score=relevance,
            dores_principais=dores,
            atributos_conversao=atributos,
            aspectos_controversos=controversos,
            red_flags=red_flags,
            score_oportunidade=score_op,
        )

    def _compute_aspect(
        self,
        aspecto: str,
        bucket: dict,
        total_comments: int,
    ) -> IndicatorTriplet:
        count_pos = bucket["count_pos"]
        count_neg = bucket["count_neg"]
        count_neu = bucket["count_neu"]
        count_mix = bucket["count_mix"]
        freq = len(bucket["triplets"])

        # PN: frequência normalizada × intensidade negativa
        # Intensidade negativa = proporção de menções NEG sobre total do aspecto
        intensidade_neg = count_neg / freq if freq > 0 else 0.0
        score_pn = (freq / max(total_comments, 1)) * intensidade_neg

        # AP: frequência normalizada × intensidade positiva
        intensidade_pos = count_pos / freq if freq > 0 else 0.0
        score_ap = (freq / max(total_comments, 1)) * intensidade_pos

        # Controvérsia: equilíbrio entre POS e NEG
        # Máximo quando count_pos == count_neg, zero quando só POS ou só NEG
        total_polar = count_pos + count_neg
        if total_polar > 0:
            controversia = 1.0 - abs(count_pos - count_neg) / total_polar
        else:
            controversia = 0.0

        # Polaridade dominante
        counts = {"POS": count_pos, "NEG": count_neg, "NEU": count_neu, "MIX": count_mix}
        polaridade_dominante = max(counts, key=counts.__getitem__)

        # Opinião representativa: a mais frequente
        from collections import Counter
        opiniao_rep = Counter(bucket["opinions"]).most_common(1)[0][0] if bucket["opinions"] else ""

        # Confiança média
        confiancas = bucket["confiancas"]
        confianca_media = sum(confiancas) / len(confiancas) if confiancas else 0.0

        return IndicatorTriplet(
            aspecto=aspecto,
            opiniao_representativa=opiniao_rep,
            polaridade_dominante=polaridade_dominante,
            categoria_aspecto=bucket["categoria_aspecto"],
            frequencia=freq,
            confianca_media=round(confianca_media, 3),
            score_pn=round(score_pn, 4),
            score_ap=round(score_ap, 4),
            controversia=round(controversia, 3),
            _count_pos=count_pos,
            _count_neg=count_neg,
            _count_neu=count_neu,
        )

    @staticmethod
    def _extract_red_flags(dores: list[IndicatorTriplet]) -> list[str]:
        """
        Gera red flags textuais a partir das dores principais.
        Red flags são aspectos NEG de categorias de formulação/claim.
        """
        FLAG_CATEGORIES = {
            "ATIVO_INGREDIENTE", "CLAIM_EFICACIA", "TEXTURA_PRODUTO", "APLICACAO"
        }
        flags = []
        for dor in dores:
            if dor.categoria_aspecto in FLAG_CATEGORIES and dor.score_pn >= 0.5:
                flags.append(
                    f"{dor.aspecto} → {dor.opiniao_representativa} "
                    f"(PN={dor.score_pn:.2f}, {dor.frequencia} menções)"
                )
        return flags[:5]  # máximo 5 red flags

    @staticmethod
    def _score_oportunidade(
        indicators: list[IndicatorTriplet],
        total_comments: int,
    ) -> float:
        """
        Score de oportunidade: AP média - PN média, normalizado em 0–10.
        """
        if not indicators:
            return 0.0
        ap_media = sum(i.score_ap for i in indicators) / len(indicators)
        pn_media = sum(i.score_pn for i in indicators) / len(indicators)
        raw = (ap_media - pn_media + 0.5) * 10  # offset para evitar negativos
        return round(max(0.0, min(10.0, raw)), 1)

    # ------------------------------------------------------------------
    # Helpers de inferência de categoria e segmento
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_categoria(comment: dict) -> str:
        """Infere a categoria do produto a partir do comentário."""
        # Preferência: campo macro_theme do vídeo
        macro = comment.get("macro_theme", "")
        if macro:
            return macro

        # Fallback: campo do vídeo no schema V1
        video = comment.get("video", {})
        if isinstance(video, dict):
            memo = video.get("netnography_video_memo", {})
            if isinstance(memo, dict):
                return memo.get("macro_theme", "indefinido")
        return "indefinido"

    @staticmethod
    def _infer_segmento(comment: dict) -> str:
        """Infere o segmento HNR do comentário."""
        # ctx_from_comment já faz isso — reutiliza a lógica de types.py
        from vozes_da_comunidade.types import ctx_from_comment
        return ctx_from_comment(comment).segmento_hnr
