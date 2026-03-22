# PRD — Memória Viva
**Versão:** 1.0 | **Status:** Draft validado | **Data:** Março 2026

---

## Executive Summary

O sistema multi-agente de briefing de produto da Embelleze/Novex tem 7 agentes que executam análises sofisticadas — mas cada execução começa do zero. Sem memória persistente, o sistema é stateless entre runs: não aprende com briefings aprovados, não lembra por que uma ideia foi rejeitada, não acumula inteligência de consumidor ao longo do tempo.

A **Memória Viva** é o componente que transforma o sistema de "ferramenta que responde" em "sistema que aprende". Inspirada na arquitetura de memória do OpenClaw.

---

## Problemas (em 4 partes)

**Problema 1 — Aprendizado perdido**
Comitê rejeita briefing. Na semana seguinte, PM submete ideia similar. Agente 1 avalia só contra Código Genético estático. Mesmo briefing fraco é gerado.

**Problema 2 — Inteligência que não acumula**
Agente 4 analisa 600 comentários. Duas semanas depois, reanálise dos mesmos comentários do zero.

**Problema 3 — Calibração que nunca acontece**
BVS Preditivo de 71. BVS Real: 58. Sistema não sabe, não se recalibra.

**Problema 4 — Contexto inacessível**
30 briefings em 6 meses no SQLite como checkpoints — mas não numa forma que o LLM possa usar como contexto. Padrões existem mas são inacessíveis.

---

## Objetivos

| ID | Objetivo |
|---|---|
| G1 | Aprendizado acumulativo: sistema mais inteligente a cada briefing |
| G2 | Calibração contínua: BVS Preditivo converge para Real (meta: desvio < 15% após 10 lançamentos) |
| G3 | Contexto sempre disponível: qualquer agente acessa inteligência relevante |
| G4 | Auditabilidade total: cada decisão tem origem rastreável |
| G5 | Extensibilidade: novos agentes se conectam sem refatoração |

---

## O que o OpenClaw resolveu (padrões utilizados)

| Conceito OpenClaw | Adaptação para Embelleze/Novex |
|---|---|
| Session JSONL (Hot) | LangGraph State em SQLite via SqliteSaver |
| Workspace Files (Warm) | ChromaDB coleções por tipo de memória |
| JSONL Histórico (Cold) | Filesystem com Markdown arquivado por briefing |
| Pre-compaction Flush | Post-briefing Memory Flush (fim de execução) |
| Session Pruning (soft/hard) | Memory Aging (soft-trim >90 dias, hard-clear >1 ano) |
| AGENTS.md / SOUL.md | `BRAND_MEMORY.md` — sempre injetado |
| memory/YYYY-MM-DD.md | `briefings/YYYY-MM-DD.md` — log diário |
| /compact command | `memory compact [segmento]` |
| Session Maintenance | Memory Maintenance automático (cron semanal) |

---

## Requisitos Funcionais Core (MVP)

| ID | Requisito |
|---|---|
| MEM-001 | Escrita automática pós-briefing |
| MEM-002 | Leitura de contexto pré-execução |
| MEM-003 | Store de Memória Quente (Hot Store): SQLite |
| MEM-004 | Store de Memória Morna (Warm Store): ChromaDB |
| MEM-005 | Store de Memória Fria (Cold Store): Filesystem Markdown |
| MEM-006 | Memory Flush pós-decisão do Comitê |
| MEM-007 | Consulta de memória sob demanda |

---

## Métricas de Sucesso

| Métrica | Baseline | Meta 3 meses | Meta 6 meses |
|---|---|---|---|
| Desvio BVS Preditivo vs Real | N/A | < 25% | < 15% |
| Taxa de rejeição por "padrão já visto" | 0% | > 20% dos NO-GOs | > 40% dos NO-GOs |
| Tempo de injeção de contexto | N/A | < 2s | < 1s |
| Cobertura de segmentos | 0 | 3 segmentos (HNR) | 8 segmentos |
| NPS do PM com qualidade dos briefings | Baseline T0 | +15% | +30% |

---

## Por que a Memória Viva muda o jogo

```
MÊS 1 — INGÊNUO
Padrões de briefing: vazio
Calibração de BVS:  sem dados
Qualidade:          boa, mas genérica

MÊS 6 — SABEDORIA OPERACIONAL
Padrões de briefing: ~25 briefings acumulados
Desvio BVS:         de ~11% para ~7%
Qualidade:          melhorou ~35%

MÊS 12 — ATIVO ESTRATÉGICO
Padrões de briefing: ~50 briefings
Desvio BVS:         de ~11% para ~5%
Taxa NO-GO evitados: >40%
Qualidade:          melhorou ~50%

O SISTEMA SABE MAIS SOBRE BRIEFINGS NOVEX
DO QUE QUALQUER PM QUE ENTROU ONTEM.
```

A pergunta certa não é "vale a pena implementar a Memória Viva?"

A pergunta certa é: **"em quanto tempo o sistema sem memória se torna um passivo comparado ao sistema com memória?"**

Resposta estimada: **mês 3.**
