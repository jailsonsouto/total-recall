"""
Interface abstrata para extratores ASTE.

Todo extrator implementa ASTEExtractor.
O pipeline não precisa saber qual implementação está usando.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from vozes_da_comunidade.types import ASTETriplet, ExtractionContext, ctx_from_comment


class ASTEExtractor(ABC):
    """
    Interface de extração de triplas ASTE.

    Implementações:
      BERTimbauExtractor  — Plano A: BIO tagging via DINAMICA-ABSA (fine-tuned)
      SLMExtractor        — Plano B: Qwen2.5 via ollama ou MLX-LM
    """

    @abstractmethod
    def extract(self, text: str, context: ExtractionContext) -> list[ASTETriplet]:
        """
        Extrai triplas ASTE de um único comentário.

        Args:
            text:    Texto pré-processado (text_for_model do schema V1).
            context: Contexto extraído do schema V1 (segmento, tema, sinais).

        Returns:
            Lista de ASTETriplet. Pode ser vazia se nenhuma tripla for encontrada.
        """
        ...

    @abstractmethod
    def is_ready(self) -> bool:
        """
        Indica se o extrator está pronto para uso.

        BERTimbauExtractor: False enquanto não houver checkpoint fine-tuned.
        SLMExtractor: sempre True (zero-shot funciona de imediato).
        """
        ...

    def batch_extract(
        self,
        comments: list[dict],
    ) -> list[list[ASTETriplet]]:
        """
        Extrai triplas de um lote de comentários.

        Implementação padrão: extração serial comentário a comentário.
        BERTimbauExtractor sobrescreve com batch real (50-100 comentários/s no M1).

        Args:
            comments: Lista de dicts no schema V1 com campos:
                      text_for_model, netnography, linguistic_signals, etc.

        Returns:
            Lista de listas — uma lista de triplas por comentário.
        """
        results = []
        for comment in comments:
            text = comment.get("text_for_model", "")
            ctx = ctx_from_comment(comment)
            try:
                triplets = self.extract(text, ctx)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "Falha ao extrair triplas do comentário %s: %s",
                    comment.get("comment_id", "?"),
                    exc,
                )
                triplets = []
            results.append(triplets)
        return results

    @property
    def name(self) -> str:
        """Nome do extrator para logging e rastreabilidade."""
        return self.__class__.__name__
