"""
models.py — Estruturas de dados da Memória Viva
================================================

"Modelos" aqui NÃO são modelos de IA. São como formulários:
definem a FORMA dos dados que circulam pelo sistema.

ANALOGIA:
    Se o banco de dados é o armário, os modelos são as etiquetas
    nas gavetas. Eles dizem o que vai em cada lugar e garantem
    que todos os componentes falem a mesma língua.

POR QUE ISSO IMPORTA:
    Quando o Agente 8 lê a memória, ele precisa saber exatamente
    que formato os dados vão ter. Os modelos garantem isso.
    Se amanhã adicionarmos um campo novo, mudamos aqui e o
    sistema inteiro sabe.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class BriefingThread:
    """
    Um briefing em andamento ou já finalizado.

    Cada vez que um PM submete uma ideia de produto,
    um BriefingThread é criado. Ele acompanha o briefing desde
    a submissão até a decisão final do Comitê.

    CICLO DE VIDA:
        running → pending_committee → committee_go/committee_no_go → archived

    Exemplo:
        BriefingThread(
            thread_id="abc-123",
            product_idea="sérum de transição com quinoa",
            pm_id="jay",
            segment="transicao-capilar",
            iam_score=78.0,
            bvs_preditivo=7.2,
        )
    """
    thread_id: str                           # ID único (UUID gerado automaticamente)
    product_idea: str                        # "sérum de transição com quinoa"
    pm_id: str = "jay"                       # quem submeteu (jay, ana, etc.)
    segment: Optional[str] = None            # "transicao-capilar", "reconstrucao", etc.
    current_status: str = "running"          # fase atual do ciclo de vida

    # ── Scores calculados pelos 7 agentes ─────────────────────
    iam_score: Optional[float] = None        # Agente 1: Alinhamento de Marca (0-100)
    bvs_preditivo: Optional[float] = None    # Agente 2: BVS previsto (0-10)
    bvs_real: Optional[float] = None         # Preenchido 3-6 meses depois (ADR-007)
    rice_score: Optional[float] = None       # Agente 5: Reach×Impact×Confidence÷Effort
    icb_score: Optional[float] = None        # Agente 7: Coerência de Briefing (0-100)

    # ── Decisão do Comitê (preenchido pelo Committee Flush) ───
    committee_decision: Optional[str] = None   # 'GO', 'NO-GO', 'HOLD'
    committee_date: Optional[datetime] = None
    committee_reasons: Optional[list[str]] = None
    committee_notes: Optional[str] = None

    # ── Controle interno ──────────────────────────────────────
    memory_flush_done: bool = False
    created_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None


@dataclass
class MemoryPattern:
    """
    Um padrão aprendido pela memória.

    Quando o Comitê aprova ou rejeita um briefing, o sistema
    extrai o "padrão" — o que funcionou ou não funcionou.
    Esses padrões são buscados automaticamente quando um briefing
    similar é submetido no futuro.

    Exemplos reais:
        - "Séruns com ativo > R$X/kg são rejeitados na Onda 2"
        - "Briefings de transição capilar com BVS > 7 são aprovados"
        - "Embalagens com apelo infantil rejeitadas para linha profissional"
    """
    id: str                        # UUID único
    pattern_type: str              # 'approval', 'rejection', 'segment_insight'
    segment: Optional[str]         # "transicao-capilar", "reconstrucao"
    description: str               # descrição legível do padrão
    occurrences: int = 1           # quantas vezes esse padrão apareceu
    confidence: str = "baixa"      # 'baixa', 'média', 'alta'
    is_active: bool = True
    rejection_alert: bool = False  # se True, alerta em briefings futuros
    source_thread_ids: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    """
    Resultado de uma busca na memória (vetorial ou keyword).

    Quando o sistema busca por padrões similares a uma nova ideia,
    cada resultado traz:
        - content: o texto encontrado
        - collection: de qual "gaveta" veio (briefing_patterns, segment_insights, etc.)
        - distance: quão distante da busca (MENOR = MAIS similar)
        - metadata: informações extras (segmento, decisão, scores, etc.)
    """
    content: str
    collection: str
    distance: float
    metadata: dict = field(default_factory=dict)


@dataclass
class MemoryContext:
    """
    Contexto montado para injeção pré-execução.

    Este é o "pacote de conhecimento" que o Agente 8 prepara
    ANTES de qualquer briefing rodar. É injetado nos outros
    agentes para que eles não partam do zero.

    Contém:
        - Código Genético da marca (sempre presente)
        - Padrões históricos de briefings similares
        - Alertas de rejeição (ATENÇÃO: padrão já rejeitado antes!)
        - Calibrações de score (ex: "BVS tende a ser otimista em 0.4")
        - Insights do segmento relevante
    """
    brand_context: str = ""
    historical_patterns: list[SearchResult] = field(default_factory=list)
    score_calibrations: dict = field(default_factory=dict)
    segment_insights: list[SearchResult] = field(default_factory=list)
    rejection_alerts: list[str] = field(default_factory=list)
    total_tokens_estimate: int = 0

    def format_for_injection(self) -> str:
        """
        Formata o contexto como texto para injeção nos agentes.

        Este texto é o que os agentes realmente "leem" antes de
        começar a trabalhar. É como um briefing do briefing.
        """
        parts = []

        if self.brand_context:
            parts.append("## Código Genético da Marca\n" + self.brand_context)

        if self.rejection_alerts:
            alerts = "\n".join(f"- {a}" for a in self.rejection_alerts)
            parts.append(f"## ⚠ ALERTAS DE REJEIÇÃO\n{alerts}")

        if self.historical_patterns:
            patterns = "\n".join(
                f"- [{r.collection}] {r.content}" for r in self.historical_patterns
            )
            parts.append(f"## Padrões Históricos\n{patterns}")

        if self.score_calibrations:
            adj = self.score_calibrations.get("bvs_adjustment", 0)
            conf = self.score_calibrations.get("confidence_level", "baixa")
            n = self.score_calibrations.get("n_data_points", 0)
            parts.append(
                f"## Calibrações de Score\n"
                f"- Ajuste BVS: {adj:+.2f} (confiança: {conf}, baseado em {n} briefings)"
            )

        if self.segment_insights:
            insights = "\n".join(
                f"- {r.content}" for r in self.segment_insights
            )
            parts.append(f"## Insights do Segmento\n{insights}")

        return "\n\n---\n\n".join(parts)
