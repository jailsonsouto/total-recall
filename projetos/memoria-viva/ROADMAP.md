# Memória Viva — Roadmap de Implementação

## Visão geral
4 estágios progressivos. Cada estágio é utilizável e agrega valor independentemente.

---

## Estágio 1 — Amnésica (hoje, sem implementação)
Cada briefing começa do zero. Nenhuma aprendizagem entre runs.
Comparável a: Nano-claw (stateless por design).

---

## Estágio 2 — Episódica (MVP — 4 semanas)
**Meta:** sistema lembra de briefings passados e alerta sobre padrões de rejeição.

### Entregáveis
- [ ] Hot Store: schema SQL completo (ver `docs/ARQUITETURA.md`)
- [ ] Agente 8 — Memory Manager (esqueleto)
- [ ] Momento 1: Memory Read (pré-execução)
- [ ] Momento 2: Post-briefing Flush
- [ ] Cold Store: estrutura de pastas + BRAND_MEMORY.md
- [ ] Integração com Agente 1 (injeção de contexto)

### Métricas de validação
- Contexto injetado em < 2s
- Flush pós-briefing nunca skippado (transação atômica)
- Alertas de padrão de rejeição funcionando

Comparável a: OpenClaw com workspace files.

---

## Estágio 3 — Semântica (Fase 2 — ~3 meses)
**Meta:** busca por significado + calibração Bayesiana de scores.

### Entregáveis
- [ ] Warm Store: ChromaDB local com coleções definidas
- [ ] Busca semântica em `briefing_patterns` e `segment_insights`
- [ ] Calibração de BVS Preditivo (Bayesian updating após 5 decisões)
- [ ] Momento 3: Committee Memory Flush (WAL mode, nunca pode falhar)
- [ ] Integração com Agentes 2, 4 e 5
- [ ] MIP — Memory Integration Protocol para extensibilidade

### Métricas de validação
- Desvio BVS Preditivo vs Real < 25%
- Cobertura de 3 segmentos (HNR)
- Taxa de rejeição por "padrão já visto" > 20% dos NO-GOs

Comparável a: sistema proprietário com RAG.

---

## Estágio 4 — Estratégica (Fase 3 — 6+ meses)
**Meta:** detecção de padrões que humanos não veriam + RL leve.

### Entregáveis
- [ ] TD Learning com dados de venda reais (BVS Real vs Preditivo)
- [ ] Exploration/exploitation balanceado
- [ ] Momento 4: manutenção periódica automatizada (cron semanal)
- [ ] Migration Hot Store → ChromaDB (Pinecone em produção)
- [ ] Dashboard de saúde da memória

### Métricas de validação
- Desvio BVS Preditivo vs Real < 15%
- Taxa de rejeição por "padrão já visto" > 40% dos NO-GOs
- NPS do PM com qualidade dos briefings +30% vs baseline

Comparável a: sistema de inteligência de produto com RL leve.

---

## Decisão de onde começar
O MVP (Estágio 2) é suficiente para agregar valor imediato:
- Elimina o Problema 1 (aprendizado perdido com rejeições do Comitê)
- Resolve parcialmente o Problema 4 (contexto inacessível)
- Não requer ChromaDB nem calibração — só SQLite e Markdown

Comece pelo Momento 1 (Memory Read) + Cold Store (BRAND_MEMORY.md).
É o menor ciclo que entrega valor real.
