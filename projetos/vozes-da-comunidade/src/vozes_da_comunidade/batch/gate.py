"""
SemanticGate — segundo filtro do pipeline offline.

Recebe comentários já aceitos pelo Router e classifica cada um em:
  aste_ready      → tem aspecto + opinião expressos — vale chamar o extrator
  absa_implicit   → tem sentimento mas sem span opinativo claro — extrator pode gerar ruído
  claim_question  → pergunta, conselho ou claim sem opinião própria
  off_topic       → nenhuma relação com produto/categoria

Propósito:
  Economizar chamadas de API (extrator só recebe aste_ready) e
  preservar a trilha de decisão por comentário para auditoria.

Lógica:
  Heurísticas de texto PT-BR. Calibradas nos dados reais do benchmark n=300
  onde 71% dos comentários aceitos pelo Router eram aste_ready.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------

class GateClass(Enum):
    aste_ready      = "aste_ready"
    absa_implicit   = "absa_implicit"
    claim_question  = "claim_question"
    off_topic       = "off_topic"


@dataclass
class GateDecision:
    """Decisão do gate para um comentário."""
    classification: GateClass   # NÃO é gate_class — atributo correto é classification
    reason: str
    text_snippet: str = ""


@dataclass
class GateResult:
    """Resultado da classificação do gate sobre uma lista de comentários."""
    aste_ready:     list[dict] = field(default_factory=list)
    absa_implicit:  list[dict] = field(default_factory=list)
    claim_question: list[dict] = field(default_factory=list)
    off_topic:      list[dict] = field(default_factory=list)
    decisions:      list[GateDecision] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            len(self.aste_ready)
            + len(self.absa_implicit)
            + len(self.claim_question)
            + len(self.off_topic)
        )

    def summary(self) -> str:
        t = self.total or 1
        return (
            f"Gate: {self.total} comentários classificados — "
            f"aste_ready={len(self.aste_ready)} ({len(self.aste_ready)/t:.0%}) | "
            f"absa_implicit={len(self.absa_implicit)} ({len(self.absa_implicit)/t:.0%}) | "
            f"claim_question={len(self.claim_question)} ({len(self.claim_question)/t:.0%}) | "
            f"off_topic={len(self.off_topic)} ({len(self.off_topic)/t:.0%})"
        )


# ---------------------------------------------------------------------------
# Padrões heurísticos (calibrados no corpus TikTok PT-BR)
# ---------------------------------------------------------------------------

# Indicadores de pergunta / conselho / claim sem opinião própria
_QUESTION_PATTERNS = re.compile(
    r"[?？]"                                    # ponto de interrogação
    r"|^\s*(alguém|vc|você|qual|como|onde|quando|por que|pq|oq|o que|quem|tem|existe|vale|funciona)"
    r"|\b(recomendam|recomendam|indica|indicam|testou|experimentou|já usou|qual usam)\b",
    re.IGNORECASE | re.MULTILINE,
)

# Palavras de opinião explícita (âncoras de opinião)
_OPINION_ANCHORS = re.compile(
    r"\b(amei|odiei|gostei|não gostei|ruim|ótimo|ótima|horrível|maravilhoso|maravilhosa"
    r"|incrível|lindo|linda|perfeito|perfeita|piorou|melhorou|mudou|muda|salvou|arrasou"
    r"|decepcionei|decepcionou|recomendo|não recomendo|comprei|comprarei|compraria"
    r"|voltei|nunca mais|vale a pena|não vale|virou|virei|uso|uso há|usei|estou usando"
    r"|usando|testei|ficou|ficaram|deixou|deixaram|fez|fiz|funcionou|não funcionou"
    r"|pegou fogo|confiei|confio|transformou|transformou|não queratina|sem corante"
    r"|não uso mais|parei de usar|passei a usar|adotei|abandonei)\b"
    r"|[❤️😍😭😤🔥💪✨👏🙏💕💖]",
    re.IGNORECASE,
)

# Termos de aspecto (produto/resultado capilares)
_ASPECT_ANCHORS = re.compile(
    r"\b(creme|mascara|máscara|shampoo|condicionador|óleo|oleo|sérum|serum|finalizador"
    r"|queratina|novex|elseve|embelleze|amend|haskell|salon line|lola|widi|loreal|l'oreal"
    r"|kerastase|kérastase|pantene|dove|tresemme|garnier|cadiveu|wella|schwarzkopf"
    r"|cachos|crespo|liso|ondulado|cacheado|enrolado|cabelo|cabelos|fio|fios|mecha|mechas"
    r"|hidratação|hidratacao|reconstrução|reconstrucao|nutrição|nutricao|cronograma"
    r"|proteína|proteina|bomba|btx|botox capilar|progressiva|relaxamento"
    r"|ingrediente|ativo|resultado|efeito|textura|cheiro|perfume|embalagem|frasco|pote"
    r"|preço|preco|caro|barata|barato|custo|valor|reposição de massa|reposicao de massa"
    r"|vitamina|biotina|arginina|azeite|oliva|argam|argã|bambu|alecrim|babosa)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# SemanticGate
# ---------------------------------------------------------------------------

class SemanticGate:
    """
    Classifica comentários aceitos pelo Router em 4 classes semânticas.

    Usa heurísticas de texto PT-BR — não faz chamadas de API.
    """

    MIN_TEXT_LENGTH = 15  # abaixo disso → off_topic por padrão

    def classify_all(self, comments: list[dict]) -> GateResult:
        """Classifica uma lista de comentários e retorna GateResult."""
        result = GateResult()
        for comment in comments:
            text = self._get_text(comment)
            decision = self._classify(text)
            result.decisions.append(
                GateDecision(
                    classification=decision[0],
                    reason=decision[1],
                    text_snippet=text[:80],
                )
            )
            bucket = decision[0].value  # "aste_ready", "absa_implicit", etc.
            getattr(result, bucket).append(comment)
        return result

    def _classify(self, text: str) -> tuple[GateClass, str]:
        """Retorna (GateClass, razão) para um texto."""
        stripped = text.strip()

        # 1. Texto muito curto — sem conteúdo analítico
        if len(stripped) < self.MIN_TEXT_LENGTH:
            return GateClass.off_topic, "texto_muito_curto"

        has_opinion = bool(_OPINION_ANCHORS.search(stripped))
        has_aspect  = bool(_ASPECT_ANCHORS.search(stripped))
        is_question = bool(_QUESTION_PATTERNS.search(stripped))

        # 2. Pergunta / conselho — mesmo que mencione produto, prioridade é a pergunta
        if is_question and not has_opinion:
            return GateClass.claim_question, "pergunta_sem_opiniao_propria"

        # 3. Tem aspecto E opinião → ASTE_READY
        if has_aspect and has_opinion:
            return GateClass.aste_ready, "aspecto_e_opiniao_presentes"

        # 4. Só opinião (sem aspecto explícito) → ABSA_IMPLICIT
        if has_opinion and not has_aspect:
            return GateClass.absa_implicit, "opiniao_sem_aspecto_explicito"

        # 5. Só aspecto (sem opinião) — pode ser informativo/pergunta implícita
        if has_aspect and not has_opinion:
            if is_question:
                return GateClass.claim_question, "menciona_produto_mas_e_pergunta"
            return GateClass.absa_implicit, "menciona_produto_sem_opiniao_clara"

        # 6. Nenhum sinal relevante
        return GateClass.off_topic, "sem_aspecto_nem_opiniao"

    @staticmethod
    def _get_text(comment: dict) -> str:
        return (
            comment.get("text_for_model")
            or comment.get("text")
            or ""
        )
