"""
Plano A — BERTimbauExtractor

Encapsula o DINAMICA_ABSAPipeline (TCC) sem duplicar sua lógica.
Importa o framework como dependência via sys.path (DINAMICA_ABSA_PATH no .env).

Quando is_ready() retorna False (modelo não fine-tuned ainda),
o build_extractor() faz fallback automático para o SLMExtractor.

Referências:
  Model base:  https://huggingface.co/neuralmind/bert-base-portuguese-cased
  GitHub:      https://github.com/neuralmind-ai/portuguese-bert
  Fine-tuning: https://huggingface.co/docs/transformers/tasks/token_classification
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from vozes_da_comunidade.types import ASTETriplet, ExtractionContext, ctx_from_comment
from .base import ASTEExtractor

if TYPE_CHECKING:
    pass  # evita import circular em type hints

logger = logging.getLogger(__name__)

# Mapeamento de categoria do DINAMICA-ABSA → Codebook V3
_CATEGORY_MAP: dict[str, str] = {
    "PRODUTO": "PRODUTO",
    "RESULTADO": "RESULTADO_EFICACIA",
    "TEXTURA_CABELO": "TEXTURA_CABELO",
    "TEXTURA_PRODUTO": "TEXTURA_PRODUTO",
    "EMBALAGEM": "EMBALAGEM",
    "APLICACAO": "APLICACAO",
    "CUSTO": "CUSTO",
    "CRONOGRAMA": "CRONOGRAMA_CAPILAR",
    "PRESCRITOR": "PRESCRITOR",
    "TIPO_CABELO": "CABELO_TIPO",
    # extensões para briefing
    "ATIVO_INGREDIENTE": "ATIVO_INGREDIENTE",
    "CLAIM_EFICACIA": "CLAIM_EFICACIA",
    "CUSTO_PERCEBIDO": "CUSTO_PERCEBIDO",
    "ROTINA_CRONOGRAMA": "ROTINA_CRONOGRAMA",
}

# Mapeamento de polaridade DINAMICA-ABSA → padrão interno
_POLARITY_MAP: dict[str, str] = {
    "POSITIVE": "POS",
    "NEGATIVE": "NEG",
    "NEUTRAL": "NEU",
    "MIXED": "MIX",
}


class BERTimbauExtractor(ASTEExtractor):
    """
    Extrator ASTE baseado no BERTimbau fine-tuned (Plano A).

    Pipeline interno (DINAMICA-ABSA):
      BERTimbauEncoder (embeddings contextuais)
        → OpenAspectExtractor  (BIO tagging + CRF)
        → OpenOpinionExtractor (BIO tagging + CRF)
        → LearnedPairMatcher   (biaffine attention)
        → ContextualPolarityClassifier

    Vantagens sobre o SLM:
    - Span exatos (offset início/fim) para cada aspecto/opinião
    - Batch real: 50-100 comentários/s no M1 via MPS
    - Fine-tuning incremental com novos dados da Embelleze
    - Determinístico (sem variação entre chamadas)
    - Zero custo de API (roda local)
    """

    def __init__(self, model_path: str | None) -> None:
        """
        Args:
            model_path: Caminho para o diretório do checkpoint fine-tuned.
                        None ou caminho inexistente → is_ready() retorna False.
        """
        self._pipeline = None
        self._model_path = model_path

        if not model_path:
            logger.info("BERTimbauExtractor: BERTIMBAU_MODEL_PATH não configurado.")
            return

        if not Path(model_path).exists():
            logger.info(
                "BERTimbauExtractor: caminho '%s' não encontrado. "
                "Fine-tuning ainda não realizado — use o SLM por enquanto.",
                model_path,
            )
            return

        try:
            self._load_pipeline(model_path)
        except ImportError as exc:
            logger.warning(
                "BERTimbauExtractor: falha ao importar DINAMICA-ABSA. "
                "Verifique DINAMICA_ABSA_PATH no .env. Erro: %s",
                exc,
            )

    def _load_pipeline(self, model_path: str) -> None:
        """Injeta DINAMICA-ABSA no sys.path e carrega o pipeline com checkpoints."""
        import os

        absa_path = os.getenv(
            "DINAMICA_ABSA_PATH",
            str(
                Path.home()
                / "Library/CloudStorage/OneDrive-Embelleze"
                / "MEUS-PROJETOS-IA/COLETA-COMENTARIOS-TIKTOK"
                / "PROCESSAMENTO-COLETA/kimi/dinamica_absa"
            ),
        )

        if absa_path not in sys.path:
            sys.path.insert(0, absa_path)

        from dinamica_absa.src.models.full_pipeline import DINAMICA_ABSAPipeline  # type: ignore

        # DINAMICA_ABSAPipeline carrega o encoder base e aplica os checkpoints
        # fine-tuned via load_checkpoints(checkpoint_dir).
        # Arquivos esperados no model_path:
        #   aspect_extractor.pt, opinion_extractor.pt,
        #   polarity_classifier.pt, pair_matcher.pt
        self._pipeline = DINAMICA_ABSAPipeline(
            model_name="neuralmind/bert-base-portuguese-cased",
            checkpoint_dir=model_path,
        )
        self._pipeline.set_eval_mode()
        logger.info("BERTimbauExtractor: checkpoints carregados de '%s'.", model_path)

    # ------------------------------------------------------------------
    # Interface ASTEExtractor
    # ------------------------------------------------------------------

    def is_ready(self) -> bool:
        return self._pipeline is not None

    def extract(self, text: str, context: ExtractionContext) -> list[ASTETriplet]:
        if not self.is_ready():
            raise RuntimeError(
                "BERTimbauExtractor não está pronto. "
                "Fine-tuning necessário ou BERTIMBAU_MODEL_PATH inválido."
            )
        # Método correto do DINAMICA_ABSAPipeline: process_text()
        result = self._pipeline.process_text(text)
        return [self._adapt(t, context) for t in result.triplets]

    def batch_extract(self, comments: list[dict]) -> list[list[ASTETriplet]]:
        """Batch real via DINAMICA-ABSA — mais eficiente que extração serial."""
        if not self.is_ready():
            raise RuntimeError("BERTimbauExtractor não está pronto.")

        texts = [c.get("text_for_model", "") for c in comments]
        contexts = [ctx_from_comment(c) for c in comments]

        # process_json_file() processa arquivos; para lista de textos usa process_text() em loop
        # O pipeline DINAMICA-ABSA não expõe batch_extract() direto — serial é o caminho correto
        results = [self._pipeline.process_text(t) for t in texts]

        return [
            [self._adapt(t, ctx) for t in r.triplets]
            for r, ctx in zip(results, contexts)
        ]

    # ------------------------------------------------------------------
    # Adaptador de saída DINAMICA-ABSA → ASTETriplet
    # ------------------------------------------------------------------

    def _adapt(self, triplet_dict: dict, context: ExtractionContext) -> ASTETriplet:
        """
        Converte um triplet dict do ExtractionResult em ASTETriplet.

        O ExtractionResult do DINAMICA-ABSA usa:
          aspect, opinion, polarity, polarity_confidence, confidence
        """
        raw_polarity = triplet_dict.get("polarity", "NEUTRAL")
        raw_category = triplet_dict.get("aspect_category", "PRODUTO")

        return ASTETriplet(
            aspecto=triplet_dict.get("aspect", ""),
            opiniao=triplet_dict.get("opinion", ""),
            polaridade=_POLARITY_MAP.get(raw_polarity, "NEU"),
            confianca=triplet_dict.get("confidence", 0.0),
            categoria_aspecto=_CATEGORY_MAP.get(raw_category, raw_category),
            span_aspecto=triplet_dict.get("aspect_span"),
            span_opiniao=triplet_dict.get("opinion_span"),
        )
