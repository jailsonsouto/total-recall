"""
Factory de extratores ASTE com fallback automático.

Uso:
    from vozes_da_comunidade.extractors import build_extractor

    extractor = build_extractor()
    triplets = extractor.extract(text, context)

O motor é selecionado via variável de ambiente ASTE_BACKEND:
  bertimbau → BERTimbauExtractor (Plano A — requer checkpoint fine-tuned)
  slm       → SLMExtractor      (Plano B — funciona zero-shot)

Se ASTE_BACKEND=bertimbau mas o modelo não estiver disponível,
o sistema emite um aviso e usa o SLMExtractor automaticamente.
"""
from __future__ import annotations

import logging

from vozes_da_comunidade import config as cfg
from .base import ASTEExtractor
from .bertimbau import BERTimbauExtractor
from .slm import SLMExtractor

logger = logging.getLogger(__name__)

__all__ = [
    "ASTEExtractor",
    "BERTimbauExtractor",
    "SLMExtractor",
    "build_extractor",
]


def build_extractor() -> ASTEExtractor:
    """
    Constrói o extrator ASTE conforme a configuração.

    Fallback automático:
        ASTE_BACKEND=bertimbau + modelo ausente → SLMExtractor com aviso

    Returns:
        ASTEExtractor pronto para uso (is_ready() garantido como True).
    """
    backend = cfg.ASTE_BACKEND.lower()

    if backend == "bertimbau":
        extractor = BERTimbauExtractor(cfg.BERTIMBAU_MODEL_PATH)
        if extractor.is_ready():
            logger.info("Usando BERTimbauExtractor (Plano A).")
            return extractor

        logger.warning(
            "BERTimbauExtractor não disponível "
            "(BERTIMBAU_MODEL_PATH=%s). "
            "Fallback automático para SLMExtractor (Plano B). "
            "Para usar o Plano A: realize o fine-tuning e configure BERTIMBAU_MODEL_PATH.",
            cfg.BERTIMBAU_MODEL_PATH,
        )
        return _build_slm()

    if backend == "slm":
        return _build_slm()

    raise ValueError(
        f"ASTE_BACKEND inválido: '{cfg.ASTE_BACKEND}'. "
        "Use 'bertimbau' ou 'slm'."
    )


def _build_slm() -> SLMExtractor:
    extractor = SLMExtractor(model=cfg.SLM_MODEL, backend=cfg.SLM_BACKEND)
    logger.info(
        "Usando SLMExtractor (Plano B): backend=%s model=%s",
        cfg.SLM_BACKEND,
        cfg.SLM_MODEL,
    )
    return extractor
