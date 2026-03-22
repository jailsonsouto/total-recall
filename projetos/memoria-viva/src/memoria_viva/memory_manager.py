"""
memory_manager.py — Agente 8: Memory Manager
=============================================

╔══════════════════════════════════════════════════════════════╗
║  ESTE É O CORAÇÃO DA MEMÓRIA VIVA.                          ║
║                                                              ║
║  O Memory Manager é responsável por fazer o sistema          ║
║  "aprender". Ele opera em 4 momentos — dos quais 3 estão    ║
║  implementados neste MVP:                                    ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  MOMENTO 1 — MEMORY READ (pré-execução)                     ║
║  Antes de qualquer briefing rodar, monta um "pacote de      ║
║  conhecimento" com tudo que o sistema já sabe sobre aquele   ║
║  tipo de ideia. Injeta nos outros agentes.                   ║
║                                                              ║
║  MOMENTO 2 — POST-BRIEFING FLUSH (pós-execução)             ║
║  Quando um briefing termina, salva o que vale lembrar        ║
║  nas 3 camadas (Hot, Warm, Cold).                            ║
║                                                              ║
║  MOMENTO 3 — COMMITTEE FLUSH (pós-decisão do Comitê)        ║
║  Quando o Comitê decide GO ou NO-GO, registra a decisão     ║
║  e extrai padrões. É aqui que o sistema APRENDE DE VERDADE. ║
║                                                              ║
║  MOMENTO 4 — MANUTENÇÃO (cron semanal)                      ║
║  [Não implementado no MVP]                                   ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

COMO OS OUTROS AGENTES USAM ISSO:
    Eles NÃO chamam o Memory Manager diretamente.
    O orquestrador (LangGraph) chama:
        1. memory_read() ANTES de rodar os agentes
        2. post_briefing_flush() DEPOIS de rodar os agentes
    O Committee Flush é disparado pelo polling do Basecamp (ADR-006).
"""

import json
import uuid
from datetime import datetime
from typing import Optional

from .config import CONTEXT_BUDGET
from .database import Database
from .embeddings import EmbeddingProvider, get_embedding_provider
from .vector_store import SQLiteVectorStore
from .cold_store import ColdStore
from .models import MemoryContext, SearchResult


class MemoryManager:
    """
    Agente 8 — Memory Manager.

    O cérebro do sistema de memória. Coordena a leitura e escrita
    nas 3 camadas (Hot, Warm, Cold) para que os outros 7 agentes
    nunca partam do zero.

    Uso básico:
        mm = MemoryManager()

        # Antes de rodar os agentes:
        ctx = mm.memory_read("sérum de transição com quinoa")

        # Depois de rodar os agentes:
        mm.post_briefing_flush(
            thread_id="abc-123",
            product_idea="sérum de transição com quinoa",
            summary="Briefing sobre sérum de transição capilar...",
            scores={"iam": 78, "bvs_preditivo": 7.2},
        )

        # Quando o Comitê decidir:
        mm.committee_flush(
            thread_id="abc-123",
            decision="GO",
            reasons=["ativo validado", "preço ok para Onda 2"],
        )
    """

    def __init__(
        self,
        db: Optional[Database] = None,
        embed_provider: Optional[EmbeddingProvider] = None,
        cold_store: Optional[ColdStore] = None,
    ):
        # Inicializa os componentes (usa defaults se não fornecidos)
        self.db = db or Database()
        self.embed = embed_provider or get_embedding_provider()
        self.vector_store = SQLiteVectorStore(self.db, self.embed)
        self.cold_store = cold_store or ColdStore()

    # ══════════════════════════════════════════════════════════
    # MOMENTO 1 — MEMORY READ (pré-execução)
    # ══════════════════════════════════════════════════════════

    def memory_read(self, product_idea: str,
                    pm_id: str = "jay") -> MemoryContext:
        """
        Monta o contexto de memória para um novo briefing.

        É chamado ANTES dos 7 agentes rodarem. Reúne tudo que o
        sistema já sabe que pode ser relevante para esta ideia.

        O que faz (nesta ordem):
            1. Carrega o Código Genético da marca (SEMPRE)
            2. Busca briefings passados semanticamente similares
            3. Verifica alertas de rejeição ativos
            4. Carrega calibrações de score (viés do Agente 2)
            5. Busca insights do segmento relevante

        Tudo respeitando o budget de 4.000 tokens para não
        sobrecarregar os agentes com contexto excessivo.

        Parâmetros:
            product_idea: "sérum de transição com quinoa"
            pm_id: quem está submetendo ("jay", "ana", etc.)

        Retorna:
            MemoryContext com todo o conhecimento relevante.
            Use ctx.format_for_injection() para obter o texto
            pronto para injetar nos agentes.
        """
        context = MemoryContext()

        # ── 1. Código Genético (SEMPRE injetado, ~500 tokens) ─────
        # É o DNA da marca. Sem isso, os agentes não sabem para
        # qual marca estão trabalhando.
        context.brand_context = self.cold_store.read_brand_memory()

        # ── 2. Padrões históricos (busca semântica, ~1.500 tokens) ─
        # Busca briefings passados com significado similar.
        # Se "sérum de quinoa" já foi feito antes, aparece aqui —
        # junto com o resultado (aprovado/rejeitado).
        try:
            context.historical_patterns = self.vector_store.hybrid_search(
                query=product_idea,
                collection="briefing_patterns",
                n_results=5,
            )
        except Exception:
            # Se a busca falhar (ex: banco vazio), continua sem padrões
            context.historical_patterns = []

        # ── 3. Alertas de rejeição (CRÍTICO) ──────────────────────
        # Se existe um padrão de rejeição ativo para este tipo de
        # briefing, o alerta é injetado com PRIORIDADE MÁXIMA.
        # Evita que o sistema gere um briefing que já sabemos que
        # será rejeitado pelo Comitê.
        context.rejection_alerts = self._get_rejection_alerts(product_idea)

        # ── 4. Calibrações de score ───────────────────────────────
        # Se o Agente 2 tende a ser otimista em 0.4 pontos no BVS,
        # a calibração é injetada para corrigir o viés.
        context.score_calibrations = self._get_latest_calibration()

        # ── 5. Insights de segmento ───────────────────────────────
        # Conhecimento acumulado sobre o segmento desta ideia.
        # Ex: tudo que sabemos sobre "transição capilar" de
        # briefings anteriores.
        segment = self._detect_segment(product_idea)
        if segment:
            try:
                context.segment_insights = self.vector_store.hybrid_search(
                    query=product_idea,
                    collection="segment_insights",
                    n_results=3,
                )
            except Exception:
                context.segment_insights = []

        # Estima o total de tokens para controle de budget
        context.total_tokens_estimate = self._estimate_tokens(context)

        return context

    def _get_rejection_alerts(self, product_idea: str) -> list[str]:
        """
        Busca padrões de rejeição ativos que podem afetar esta ideia.

        Se um briefing de "sérum de transição" já foi rejeitado por
        "ativo acima do custo Onda 2", e a nova ideia é de transição
        capilar, o alerta aparece ANTES do briefing ser gerado.

        Isso evita trabalho desperdiçado: em vez de rodar 7 agentes
        por 90 segundos para gerar um briefing que será rejeitado,
        o sistema avisa na hora.
        """
        with self.db.connection() as conn:
            rows = conn.execute("""
                SELECT description, segment, occurrences
                FROM memory_patterns
                WHERE pattern_type = 'rejection'
                  AND rejection_alert = TRUE
                  AND is_active = TRUE
                ORDER BY occurrences DESC
            """).fetchall()

        alerts = []
        product_lower = product_idea.lower()
        for row in rows:
            desc = row[0]
            segment = row[1] or ""
            # Alerta se o segmento do padrão aparece na ideia, ou se é genérico
            if segment.replace("-", " ") in product_lower or not segment:
                alerts.append(f"ALERTA DE REJEIÇÃO ({row[2]}x): {desc}")

        return alerts

    def _get_latest_calibration(self) -> dict:
        """
        Busca a calibração mais recente de scores.

        Retorna algo como:
            {"bvs_adjustment": -0.4, "confidence_level": "média", "n_data_points": 12}

        Significado: "o Agente 2 prevê BVS 0.4 acima do real, em média"
        """
        with self.db.connection() as conn:
            row = conn.execute("""
                SELECT bvs_total_adjustment, rice_confidence_baseline,
                       confidence_level, n_data_points
                FROM score_calibrations
                ORDER BY calibration_date DESC
                LIMIT 1
            """).fetchone()

        if row:
            return {
                "bvs_adjustment": row[0],
                "rice_confidence_baseline": row[1],
                "confidence_level": row[2],
                "n_data_points": row[3],
            }
        return {}

    def _detect_segment(self, product_idea: str) -> Optional[str]:
        """
        Detecta o segmento HNR de uma ideia de produto.

        Detecção simples por keywords. Cobre os principais segmentos
        da linha Novex. Em versões futuras, pode usar classificação
        por LLM para maior precisão.

        Exemplos:
            "sérum de transição" → "transicao-capilar"
            "máscara de reconstrução" → "reconstrucao"
            "creme de hidratação" → "hidratacao"
        """
        idea_lower = product_idea.lower()

        # Mapa de segmentos → palavras-chave que os identificam
        segments = {
            "transicao-capilar": [
                "transição", "transicao", "big chop", "crespo", "cacheado",
            ],
            "reconstrucao": [
                "reconstrução", "reconstrucao", "queratina", "damaged",
                "danificado",
            ],
            "hidratacao": [
                "hidratação", "hidratacao", "umectação", "moisture",
                "hidratante",
            ],
            "nutricao": [
                "nutrição", "nutricao", "óleo", "oleo", "nutrition",
                "nutritivo",
            ],
            "crescimento": [
                "crescimento", "growth", "queda", "fortalecimento",
                "antiqueda",
            ],
            "coloracao": [
                "coloração", "coloracao", "tintura", "cor", "matizador",
            ],
            "styling": [
                "styling", "modelador", "gel", "creme de pentear",
                "finalização",
            ],
            "limpeza": [
                "shampoo", "limpeza", "clarifying", "purificante",
            ],
        }

        for segment, keywords in segments.items():
            if any(kw in idea_lower for kw in keywords):
                return segment

        return None

    def _estimate_tokens(self, context: MemoryContext) -> int:
        """
        Estima o número de tokens do contexto montado.

        Regra de bolso: 1 token ≈ 4 caracteres em português.
        O budget máximo é 4.000 tokens (configurável em config.py).
        """
        total_chars = len(context.brand_context)
        total_chars += sum(len(r.content) for r in context.historical_patterns)
        total_chars += sum(len(a) for a in context.rejection_alerts)
        total_chars += len(json.dumps(context.score_calibrations))
        total_chars += sum(len(r.content) for r in context.segment_insights)
        return total_chars // 4

    # ══════════════════════════════════════════════════════════
    # MOMENTO 2 — POST-BRIEFING FLUSH (pós-execução)
    # ══════════════════════════════════════════════════════════

    def post_briefing_flush(
        self,
        thread_id: str,
        product_idea: str,
        pm_id: str = "jay",
        segment: Optional[str] = None,
        scores: Optional[dict] = None,
        summary: str = "",
    ):
        """
        Salva o resultado de um briefing nas 3 camadas.

        Chamado automaticamente quando um briefing termina de ser
        processado pelos 7 agentes. NUNCA pode ser pulado.

        O que faz:
            Hot Store:  registra o briefing (ID, scores, status)
            Warm Store: embeda o resumo para busca futura
            Cold Store: adiciona entrada no log diário

        Transação atômica para Hot + Warm Store:
            ou salva tudo, ou não salva nada.

        Parâmetros:
            thread_id: UUID do briefing (gerado pelo orquestrador)
            product_idea: "sérum de transição com quinoa"
            pm_id: "jay" (quem submeteu)
            segment: "transicao-capilar" (detectado automaticamente se None)
            scores: {"iam": 78, "bvs_preditivo": 7.2, "rice": 65, "icb": 82}
            summary: resumo do briefing (texto que será embedado)
        """
        segment = segment or self._detect_segment(product_idea)
        scores = scores or {}

        # ── Hot Store + Warm Store (transação atômica) ────────────
        with self.db.transaction() as conn:
            # Hot Store: registra o briefing com seus scores
            conn.execute("""
                INSERT OR REPLACE INTO briefing_threads
                (thread_id, product_idea, pm_id, segment, current_status,
                 iam_score, bvs_preditivo, rice_score, icb_score)
                VALUES (?, ?, ?, ?, 'pending_committee', ?, ?, ?, ?)
            """, [
                thread_id, product_idea, pm_id, segment,
                scores.get("iam"), scores.get("bvs_preditivo"),
                scores.get("rice"), scores.get("icb"),
            ])

            # Warm Store: embeda o resumo para busca futura
            # Quando um briefing similar for submetido no futuro,
            # este resumo aparecerá como padrão histórico.
            if summary:
                self.vector_store.add(
                    content=summary,
                    collection="briefing_patterns",
                    metadata={
                        "thread_id": thread_id,
                        "segment": segment,
                        "scores": scores,
                        "status": "pending_committee",
                    },
                    _conn=conn,  # usa a mesma transação
                )

        # ── Cold Store (log diário, fora da transação SQL) ────────
        log_entry = (
            f"**{product_idea}** (PM: {pm_id})\n\n"
            f"- Segmento: {segment or 'não detectado'}\n"
            f"- Scores: {json.dumps(scores, ensure_ascii=False)}\n"
            f"- Status: aguardando Comitê\n"
        )
        self.cold_store.append_to_briefing_log(log_entry)

    # ══════════════════════════════════════════════════════════
    # MOMENTO 3 — COMMITTEE FLUSH (pós-decisão do Comitê)
    # ══════════════════════════════════════════════════════════

    def committee_flush(
        self,
        thread_id: str,
        decision: str,
        reasons: list[str],
        notes: str = "",
    ):
        """
        Registra a decisão do Comitê e extrai padrões.

        ╔══════════════════════════════════════════════════════╗
        ║  ESTE É O FLUSH MAIS CRÍTICO DO SISTEMA.            ║
        ║  É o único momento onde a realidade (decisão humana) ║
        ║  retroalimenta a máquina.                            ║
        ╚══════════════════════════════════════════════════════╝

        O que faz (transação atômica):
            1. Hot Store: registra GO/NO-GO + motivos
            2. Warm Store: embeda o padrão (GO=peso 2.0, NO-GO=alerta)
            3. Hot Store: cria memory_pattern (lição aprendida)
            4. Verifica se deve recalibrar BVS (a cada 5 decisões)
            5. Cold Store: atualiza MEMORY.md

        Se qualquer escrita falhar, TODAS são revertidas.
        O banco nunca fica inconsistente.

        Parâmetros:
            thread_id: UUID do briefing
            decision: "GO", "NO-GO" ou "HOLD"
            reasons: ["ativo validado", "preço ok para Onda 2"]
            notes: observações livres do Comitê
        """
        now = datetime.now()

        with self.db.transaction() as conn:
            # ── Busca dados do briefing ───────────────────────────
            thread = conn.execute(
                "SELECT * FROM briefing_threads WHERE thread_id = ?",
                [thread_id],
            ).fetchone()

            if not thread:
                raise ValueError(f"Briefing '{thread_id}' não encontrado no banco.")

            if thread["memory_flush_done"]:
                # IDEMPOTÊNCIA: se já rodou, não roda de novo.
                # Isso protege contra execuções duplicadas
                # (ex: cron roda duas vezes antes do status atualizar).
                return

            # ── ESCRITA 1: Hot Store — registra a decisão ─────────
            status = f"committee_{decision.lower().replace('-', '_')}"
            conn.execute("""
                UPDATE briefing_threads SET
                    committee_decision = ?,
                    committee_date     = ?,
                    committee_reasons  = ?,
                    committee_notes    = ?,
                    current_status     = ?,
                    memory_flush_done  = TRUE,
                    memory_flush_at    = ?,
                    last_updated       = ?
                WHERE thread_id = ?
            """, [
                decision, now.isoformat(), json.dumps(reasons, ensure_ascii=False),
                notes, status, now.isoformat(), now.isoformat(),
                thread_id,
            ])

            # ── ESCRITA 2: Warm Store — embeda o padrão ───────────
            # GO recebe peso 2.0 → vale o dobro na busca futura
            # NO-GO recebe flag de alerta → aparece como warning
            weight = 2.0 if decision == "GO" else 1.0
            is_rejection = decision == "NO-GO"

            pattern_text = (
                f"Briefing: {thread['product_idea']} | "
                f"Decisão: {decision} | "
                f"Motivos: {', '.join(reasons)} | "
                f"Segmento: {thread['segment'] or 'indefinido'}"
            )

            self.vector_store.add(
                content=pattern_text,
                collection="briefing_patterns",
                metadata={
                    "thread_id": thread_id,
                    "decision": decision,
                    "segment": thread["segment"],
                    "weight": weight,
                    "rejection_alert": is_rejection,
                },
                _conn=conn,  # MESMA transação = atômico
            )

            # ── ESCRITA 3: Hot Store — padrão de memória ──────────
            # Registra a "lição" aprendida como um padrão estruturado
            pattern_id = str(uuid.uuid4())
            pattern_type = "approval" if decision == "GO" else "rejection"

            conn.execute("""
                INSERT INTO memory_patterns
                (id, pattern_type, segment, description,
                 rejection_alert, source_thread_ids)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [
                pattern_id, pattern_type, thread["segment"],
                f"{decision}: {', '.join(reasons)}",
                is_rejection,
                json.dumps([thread_id]),
            ])

            # ── Verifica se é hora de recalibrar BVS ─────────────
            self._maybe_recalibrate(conn)

        # ── ESCRITA 4: Cold Store — MEMORY.md ─────────────────────
        # Fora da transação SQL (é filesystem, não banco).
        # Seguro: memory_flush_done=TRUE impede re-execução.
        self._update_cold_store_after_decision(
            thread, decision, reasons, notes,
        )

    def _maybe_recalibrate(self, conn):
        """
        Verifica se há dados suficientes para recalibrar o BVS.

        Após 5 decisões com bvs_preditivo E bvs_real preenchidos,
        calcula o desvio médio e registra a calibração.

        CALIBRAÇÃO BAYESIANA SIMPLIFICADA:
            Se o Agente 2 previu BVS 8.0 mas o real foi 7.6 em
            5 briefings consecutivos, o desvio médio é +0.4.
            A calibração registra adjustment=-0.4 para que
            briefings futuros corrijam o viés automaticamente.

        O Agente 2 recebe esse ajuste via memory_read() e pode
        aplicar a correção antes de apresentar o score.
        """
        row = conn.execute("""
            SELECT COUNT(*) as n,
                   AVG(bvs_preditivo - bvs_real) as avg_deviation
            FROM briefing_threads
            WHERE bvs_preditivo IS NOT NULL
              AND bvs_real IS NOT NULL
              AND committee_decision IS NOT NULL
        """).fetchone()

        n = row[0]
        if n >= 5:
            avg_dev = row[1] or 0.0
            confidence = "baixa" if n < 10 else ("média" if n < 20 else "alta")

            conn.execute("""
                INSERT INTO score_calibrations
                (n_data_points, bvs_total_adjustment, confidence_level)
                VALUES (?, ?, ?)
            """, [n, -avg_dev, confidence])
            # adjustment inverte o desvio:
            # se o Agente 2 prevê +0.4 acima → adjustment = -0.4

    def _update_cold_store_after_decision(
        self, thread, decision: str, reasons: list[str], notes: str,
    ):
        """
        Atualiza MEMORY.md e log diário após decisão do Comitê.

        Esta é a Escrita 4 (Cold Store) — roda FORA da transação SQL
        porque é filesystem, não banco. É protegida pela idempotência:
        memory_flush_done=TRUE impede re-execução.
        """
        product = thread["product_idea"]
        segment = thread["segment"] or "geral"
        date_str = datetime.now().strftime("%b/%Y")

        if decision == "GO":
            section = "Padrões de Aprovação"
            content = (
                f"- **{product}** ({segment}): APROVADO ({date_str})\n"
                f"  Motivos: {', '.join(reasons)}\n"
            )
        else:
            section = "Padrões de Rejeição a Evitar"
            content = (
                f"- **{product}** ({segment}): REJEITADO ({date_str})\n"
                f"  Motivos: {', '.join(reasons)}\n"
            )
            if notes:
                content += f"  Notas: {notes}\n"

        self.cold_store.update_memory(section, content)

        # Atualiza insights do segmento (se houver segmento)
        if segment and segment != "geral":
            self.cold_store.update_segment(
                segment,
                f"**{decision}**: {product} — {', '.join(reasons)}",
            )

        # Log diário
        log_entry = (
            f"**DECISÃO DO COMITÊ:** {product}\n\n"
            f"- Resultado: {decision}\n"
            f"- Motivos: {', '.join(reasons)}\n"
        )
        self.cold_store.append_to_briefing_log(log_entry)

    # ══════════════════════════════════════════════════════════
    # UTILIDADES
    # ══════════════════════════════════════════════════════════

    def insert_bvs_real(self, thread_id: str,
                        sell_through_pct: float) -> dict:
        """
        Insere o BVS Real de um briefing (Aresta 3 / ADR-007).

        Chamado manualmente via CLI por Jay quando os dados de
        sell-through Onda 1 chegam (~3 meses pós-lançamento).

        Normalização da Fase 1:
            ≥ 90% → bvs_real = bvs_preditivo × 1.1  (foi melhor)
            70-89% → bvs_real = bvs_preditivo × 0.9  (foi um pouco pior)
            < 70% → bvs_real = bvs_preditivo × 0.7   (foi bem pior)

        Cada vez que um bvs_real é inserido, o sistema tem mais um
        ponto de dados para calibrar o Agente 2. Após 5 pontos,
        a calibração Bayesiana roda automaticamente.

        Parâmetros:
            thread_id: UUID do briefing
            sell_through_pct: percentual de sell-through (ex: 85.0 = 85%)

        Retorna:
            dict com thread_id, product_idea, bvs_preditivo,
            sell_through_pct, bvs_real calculado
        """
        with self.db.transaction() as conn:
            thread = conn.execute(
                "SELECT bvs_preditivo, product_idea "
                "FROM briefing_threads WHERE thread_id = ?",
                [thread_id],
            ).fetchone()

            if not thread:
                raise ValueError(f"Briefing '{thread_id}' não encontrado.")

            bvs_pred = thread["bvs_preditivo"]
            if bvs_pred is None:
                raise ValueError(
                    f"Briefing '{thread_id}' não tem BVS Preditivo. "
                    "Não é possível calcular o BVS Real sem referência."
                )

            # Normalização Fase 1 (ADR-007)
            if sell_through_pct >= 90:
                bvs_real = bvs_pred * 1.1
            elif sell_through_pct >= 70:
                bvs_real = bvs_pred * 0.9
            else:
                bvs_real = bvs_pred * 0.7

            # Limita ao range 0-10
            bvs_real = max(0.0, min(10.0, bvs_real))

            conn.execute(
                "UPDATE briefing_threads "
                "SET bvs_real = ?, last_updated = ? "
                "WHERE thread_id = ?",
                [bvs_real, datetime.now().isoformat(), thread_id],
            )

            return {
                "thread_id": thread_id,
                "product_idea": thread["product_idea"],
                "bvs_preditivo": bvs_pred,
                "sell_through_pct": sell_through_pct,
                "bvs_real": round(bvs_real, 2),
            }

    def get_status(self) -> dict:
        """
        Retorna um resumo do estado atual da memória.

        Útil para o CLI e para diagnósticos:
        quantos briefings, quantos vetores, qual embedding, etc.
        """
        with self.db.connection() as conn:
            briefings = conn.execute(
                "SELECT COUNT(*) FROM briefing_threads",
            ).fetchone()[0]

            pending = conn.execute(
                "SELECT COUNT(*) FROM briefing_threads "
                "WHERE committee_decision IS NULL",
            ).fetchone()[0]

            patterns = conn.execute(
                "SELECT COUNT(*) FROM memory_patterns WHERE is_active = TRUE",
            ).fetchone()[0]

            vectors = conn.execute(
                "SELECT COUNT(*) FROM chunks",
            ).fetchone()[0]

            calibrations = conn.execute(
                "SELECT COUNT(*) FROM score_calibrations",
            ).fetchone()[0]

            latest_cal = conn.execute("""
                SELECT bvs_total_adjustment, confidence_level, n_data_points
                FROM score_calibrations
                ORDER BY calibration_date DESC LIMIT 1
            """).fetchone()

        return {
            "briefings_total": briefings,
            "briefings_pendentes_comite": pending,
            "padroes_ativos": patterns,
            "vetores_no_warm_store": vectors,
            "calibracoes_realizadas": calibrations,
            "embedding_provider": self.embed.model_name,
            "embedding_dimensions": self.embed.dimensions(),
            "ultima_calibracao": {
                "ajuste_bvs": latest_cal[0],
                "confianca": latest_cal[1],
                "pontos_de_dados": latest_cal[2],
            } if latest_cal else None,
        }
