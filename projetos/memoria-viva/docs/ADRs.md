# ADRs — Architecture Decision Records
## Memória Viva | Março 2026

---

### ADR-001: SQLite unificado para Hot Store + Warm Store (não ChromaDB, não LanceDB)

**Decisão:** Usar SQLite com `sqlite-vec` (vetorial) + FTS5 (keyword) como único banco — Hot Store e Warm Store no mesmo arquivo.

**Motivos:**
- Volume projetado: 200-300 briefings/ano × 4 PMs × ~15 vetores/briefing ≈ 4.500 vetores/ano
- Busca O(n) do sqlite-vec é < 5ms até ~200k vetores — escala não atingível neste projeto
- Um único arquivo SQLite elimina a necessidade de lógica de compensação entre stores
- Committee Flush vira uma transação ACID nativa (`BEGIN/COMMIT` único) — nunca pode gerar inconsistência
- Zero dependências novas: SQLite já existe por causa do LangGraph SqliteSaver; FTS5 é built-in
- sqlite-vec mantido por Alex Garcia (Fly.io) — projeto sólido, não startup de VC
- Dados nunca saem da máquina; zero custo operacional

**Descartados:**
- ChromaDB: adiciona dependência sem entregar nada que sqlite-vec+FTS5 não entrega neste volume
- LanceDB: projeto jovem (risco real de abandono); IVF-PQ só é relevante acima de ~200k vetores
- Pinecone: dados estratégicos fora da empresa — nunca
- PostgreSQL + pgvector: resolve atomicidade, mas exige servidor; complexidade desproporcional ao volume

**Upgrade path (se busca vetorial ultrapassar 200ms):**
Migrar `SQLiteVectorStore` → `LanceDBVectorStore` em um arquivo. Nenhum agente, nenhum flush, nenhum MIP muda. Estimativa: tarde de trabalho.

**Trade-off aceito:** sem busca ANN aproximada (irrelevante para o volume projetado).

---

### ADR-002: SQLite com WAL mode para Hot Store

**Decisão:** SQLite com `PRAGMA journal_mode = WAL` como banco do Hot Store.

**Motivos:**
- Leituras concorrentes durante writes sem bloqueio
- Committee Memory Flush nunca pode ser perdido — WAL garante durabilidade mesmo em crash
- Zero configuração de servidor
- LangGraph SqliteSaver já usa SQLite nativamente

**Trade-off aceito:** não escala para múltiplos PMs simultâneos (sem problema no contexto atual — 4 PMs, uso não simultâneo).

---

### ADR-003: Markdown para Cold Store

**Decisão:** Filesystem com arquivos Markdown como camada Cold Store.

**Motivos:**
- Legível por humanos — PM pode editar `BRAND_MEMORY.md` diretamente
- LLM-friendly — Markdown é o formato nativo de contexto para modelos Claude
- Git = auditoria grátis (quem editou, quando, o quê)
- Validado em produção pelo OpenClaw e Nano-claw
- Zero custo operacional

**Trade-off aceito:** não permite buscas semânticas (para isso existe o Warm Store — sqlite-vec no mesmo arquivo).

---

### ADR-004: Claude Haiku para Agente 8 (exceto Committee Flush)

**Decisão:** Usar Claude Haiku para sínteses e extrações do Agente 8. Usar Claude Sonnet exclusivamente para o Committee Memory Flush.

**Motivos:**
- Haiku é 10-20x mais barato e suficiente para extração estruturada (flash pós-briefing, aging)
- Sonnet para Committee Flush: essa escrita é permanente, afeta todos os briefings futuros — vale o custo extra de qualidade
- Padrão análogo ao uso de modelos de embedding menores para indexação + modelos maiores para inferência

**Trade-off aceito:** maior latência no Committee Flush (~3-5s a mais). Aceitável — esse momento não é time-sensitive.

---

### ADR-005: OpenClaw como interface, não como substituto

**Decisão:** OpenClaw atua como gateway de interface multi-canal (WhatsApp/Telegram/Slack). LangGraph + CrewAI + ChromaDB resolvem a orquestração analítica.

**Motivos:**
- OpenClaw não tem RAG nativo
- OpenClaw executa agentes em sequência; o sistema requer paralelismo (Agentes 2, 3 e 4 paralelos → 90s vs 4-6min sequencial)
- LangGraph SqliteSaver provê replay de estado por checkpoint — OpenClaw não tem equivalente

**Arquitetura resultante:**
```
Jay (WhatsApp / Telegram / Slack)
          │
          ▼
    OpenClaw Gateway
    (interface + memória quente + workspace files)
          │
          ▼
    FastAPI Webhook
    (traduz mensagem → execução de workflow)
          │
          ▼
    LangGraph + CrewAI + SQLite (sqlite-vec + FTS5)
    (os 7+1 agentes de análise e memória)
          │
          ▼
    OpenClaw Gateway
    (entrega o briefing no canal preferido do PM)
```

**Trade-off aceito:** dois sistemas para manter em vez de um. Justificado pela diferença de capacidade analítica.

---

### ADR-006: Polling do Basecamp como trigger do Committee Flush (não webhook)

**Decisão:** O Committee Flush é disparado por um cron que faz polling da API do Basecamp a cada 15 minutos — não por webhook push.

**Convenção no Basecamp:**
- To-do list dedicada: `Decisões de Comitê`
- Cada briefing = um to-do (criado automaticamente pelo Agente 8 no pós-execução)
- GO → to-do marcado como concluído pelo Comitê
- NO-GO → to-do arquivado com tag `no-go` + motivos no corpo

**Fluxo:**
```
cron (15min)
    │
    ▼
Basecamp API — busca to-dos concluídos/arquivados desde último check
    │
    ├── nenhum novo → dorme
    │
    └── decisão nova encontrada
            │
            ▼
        Committee Flush (transação atômica SQLite)
            ├── Hot Store: registra decisão + razões
            ├── Warm Store: embeda padrão (GO weight 2.0 / NO-GO com rejection_alert)
            └── Cold Store: atualiza MEMORY.md (idempotente)
```

**Motivos:**
- Committee Flush não é time-sensitive — 15min de latência: zero impacto
- Zero URL pública necessária — roda 100% local, sem túnel, sem servidor exposto
- Polling é resiliente: se o cron falha uma vez, o próximo ciclo pega a decisão perdida
- Basecamp já é o sistema de registro do Comitê — sem duplicar ferramentas

**Descartado:** webhook push (exigiria URL pública acessível pelo Basecamp — ngrok ou servidor, complexidade desnecessária para este volume e latência aceitável).

**Trade-off aceito:** latência de até 15 minutos entre decisão do Comitê e flush na memória (irrelevante — o próximo briefing não começa em 15 minutos).

---

### ADR-007: BVS Real — inserção manual em fases (não bloquear por metodologia indefinida)

**Contexto:**
O BVS Preditivo é calculado pelo Agente 2 antes do lançamento. O BVS Real só existe após o lançamento — e depende de uma metodologia de medição que a Embelleze/Novex ainda está desenvolvendo (inspirada na Interbrand e na metodologia Ana Couto). A Aresta 3 era: quem insere o `bvs_real` e quando?

**Decisão:** Não bloquear a implementação aguardando a metodologia definitiva. Implementar o campo `bvs_real` com inserção manual via CLI, usando proxy operacional simples na Fase 1. A metodologia evolui sobre dados reais — o contrato do campo permanece estável.

**Implementação em fases:**

```
FASE 1 — PROXY OPERACIONAL (MVP, sem custo)
Quem insere: Jay, via CLI (~3 meses pós-lançamento)
O que insere: sell-through Onda 1 vs projetado (%)

Normalização:
  ≥ 90% do projetado → bvs_real = bvs_preditivo × 1.1
  70–89%             → bvs_real = bvs_preditivo × 0.9
  < 70%              → bvs_real = bvs_preditivo × 0.7

FASE 2 — COMPOSITE (quando metodologia amadurecer)
  40% sell-through Onda 1+2
  30% ABSA retrospectivo (Agente 4, 6 meses pós-lançamento)
  30% pesquisa de percepção Ana Couto (se disponível)

FASE 3 — METODOLOGIA PRÓPRIA
  Quando BVS virar metodologia interna formalizada,
  apenas a fonte de dados muda — o campo e o motor de
  calibração permanecem inalterados.
```

**O que o sistema faz com o bvs_real:**
- Calcula desvio: `bvs_preditivo − bvs_real` por briefing
- Após 5 pontos de dados: detecta viés sistemático por segmento/Onda
- Atualiza `score_calibrations` com ajuste (Bayesian updating)
- Meta G2: desvio < 15% após 10 lançamentos

**Motivos:**
- O valor do sistema não está em prever perfeitamente — está em saber o quanto erra e em qual direção
- O campo `bvs_real` é um contrato arquitetural: "em algum momento, a realidade fala aqui"
- Proxy imperfeita que gira o loop > metodologia perfeita que paralisa a implementação
- Inspiração Interbrand: eles também levaram anos para refinar a metodologia — começaram com proxies financeiras simples

**Descartado:** aguardar definição completa da metodologia BVS antes de implementar (risco de paralisia; o campo pode aceitar qualquer valor numérico 0–10 independente da fonte).

**Trade-off aceito:** BVS Real da Fase 1 é uma proxy de desempenho comercial, não de percepção de marca — desvio entre as duas dimensões será corrigido nas fases seguintes à medida que a metodologia amadurece.
