"""
Router — primeiro filtro do pipeline offline.

Decide quais comentários do corpus TikTok são relevantes para extração ASTE.
Comentários irrelevantes (sociais, curtos, respostas do criador) são descartados
antes de chegar ao ASTEExtractor — economiza chamadas ao SLM e tempo de processamento.

Critério: campo interaction_type do schema V1.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# Tipos de interação que contêm opinião real sobre produtos
ALLOWED_TYPES: frozenset[str] = frozenset({
    "product_opinion",      # opinião direta sobre produto/resultado
    "comparison",           # compara produtos/marcas
    "technical_question",   # pergunta técnica (indica interesse/engajamento)
})

# Tipos descartados — sem conteúdo analítico
DISCARDED_TYPES: frozenset[str] = frozenset({
    "social_or_phatic",     # "linda!", "amei seu vídeo", cumprimentos
    "creator_reply",        # resposta do criador do vídeo
    "short_or_emoji_only",  # menos de 3 tokens ou só emojis
    "off_topic",            # não relacionado ao produto
    "spam",
})


@dataclass
class RouterResult:
    """Resultado do processamento do Router sobre um corpus."""

    accepted: list[dict] = field(default_factory=list)
    """Comentários aprovados — prontos para TikTokTextProcessor."""

    rejected: list[dict] = field(default_factory=list)
    """Comentários descartados — preservados para auditoria."""

    @property
    def total(self) -> int:
        return len(self.accepted) + len(self.rejected)

    @property
    def acceptance_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return len(self.accepted) / self.total

    def summary(self) -> str:
        pct = self.acceptance_rate * 100
        return (
            f"Router: {len(self.accepted)}/{self.total} comentários aceitos "
            f"({pct:.1f}%) | {len(self.rejected)} descartados"
        )


class Router:
    """
    Filtra comentários do corpus por interaction_type.

    Comentários sem campo interaction_type recebem tratamento conservador:
    se o campo eligibility.is_eligible for True → aceita; caso contrário → rejeita.
    """

    def __init__(
        self,
        allowed_types: frozenset[str] | None = None,
        min_text_length: int = 10,
    ) -> None:
        self._allowed = allowed_types or ALLOWED_TYPES
        self._min_length = min_text_length

    def route(self, comments: list[dict]) -> RouterResult:
        """
        Filtra uma lista de comentários.

        Args:
            comments: Lista de dicts no schema V1 com campo interaction_type.

        Returns:
            RouterResult com comentários aceitos e rejeitados separados.
        """
        result = RouterResult()
        for comment in comments:
            if self._is_relevant(comment):
                result.accepted.append(comment)
            else:
                result.rejected.append(comment)
        return result

    def route_file(self, json_data: dict) -> RouterResult:
        """
        Filtra comentários de um JSON completo no schema V1.

        O schema V1 tem estrutura:
          { "comments": [ {...}, {...} ] }
        ou lista direta de comentários.
        """
        if isinstance(json_data, list):
            comments = json_data
        else:
            comments = json_data.get("comments", [])
        return self.route(comments)

    def _is_relevant(self, comment: dict) -> bool:
        """Retorna True se o comentário deve ser processado."""
        # 1. Verificar eligibility explícita do schema V1
        eligibility = comment.get("eligibility", {})
        if eligibility.get("is_eligible") is False:
            return False

        # 2. Verificar interaction_type
        interaction_type = comment.get("interaction_type") or comment.get(
            "netnography", {}
        ).get("interaction_type", "")

        if interaction_type in self._allowed:
            return self._meets_length_requirement(comment)

        if interaction_type in DISCARDED_TYPES:
            return False

        # 3. interaction_type ausente ou desconhecido — fallback conservador
        if not interaction_type:
            return eligibility.get("is_eligible", False)

        # Tipo desconhecido: aceita se texto for suficientemente longo
        return self._meets_length_requirement(comment)

    def _meets_length_requirement(self, comment: dict) -> bool:
        text = comment.get("text_for_model") or comment.get("text", "")
        return len(text.strip()) >= self._min_length
