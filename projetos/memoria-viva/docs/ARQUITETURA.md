# Arquitetura Técnica — Memória Viva
## Agente 8 — Memory Manager

---

## As 3 Camadas

```
CAMADA HOT — SQLite + LangGraph State
"O que está acontecendo agora"
• Estado completo do briefing em execução
• Checkpoints de cada nó do LangGraph
• Outputs intermediários dos 7 agentes
• Scores calculados (IAM, BVS, RICE, ICB)
Tecnologia: SQLite com WAL mode + LangGraph SqliteSaver
Duração: Enquanto o briefing está ativo → depois arquivado

CAMADA WARM — SQLite (sqlite-vec + FTS5)
"O que é relevante buscar"
Tabelas no mesmo arquivo do Hot Store:
• chunks_vec (sqlite-vec) → busca semântica por proximidade vetorial
• chunks_fts (FTS5)       → busca por keyword (híbrido)
• embedding_cache         → cache de vetores já calculados
Coleções lógicas (campo metadata.collection):
• brand_memory       → Código Genético embedado
• briefing_patterns  → padrões de aprovação/rejeição
• segment_insights   → insights por segmento (HNR)
• score_calibrations → histórico de calibrações BVS/RICE
• committee_decisions→ decisões do Comitê
Tecnologia: sqlite-vec (extensão local, sem servidor)
Embedding: nomic-embed-text via Ollama (local, gratuito, 768 dims)
Duração: Persistente + atualizado pós-briefing

CAMADA COLD — Filesystem (Markdown + Git)
"O que aconteceu antes — legível por humanos"
~/.novex-memory/
  BRAND_MEMORY.md     ← Código Genético (sempre injetado)
  PM_CONTEXT.md       ← Contexto do PM
  MEMORY.md           ← Insights consolidados
  briefings/
    YYYY-MM-DD.md     ← Log diário
  segments/
    transicao-capilar.md
    reconstrucao.md
  archive/
    thread_[id]_complete.jsonl
Tecnologia: Filesystem + Git backup
```

---

## Os 4 Momentos do Agente 8

### Momento 1 — PRÉ-EXECUÇÃO (Memory Read)
*Análogo ao AGENTS.md + USER.md do OpenClaw — injetado antes de qualquer agente rodar.*

```python
async def read_memory_for_execution(product_idea, pm_context):
    # 1. Contexto sempre injetado (brand_memory + pm_context)
    brand_context = await warm_store.get_always_injected_context()

    # 2. Busca semântica por padrões históricos
    # sqlite-vec: busca por proximidade vetorial no mesmo arquivo SQLite
    historical_patterns = await warm_store.semantic_search(
        query=product_idea,
        collections=["briefing_patterns"],
        n_results=5,
        max_tokens=1500
    )

    # 3. Calibrações de score
    score_calibrations = await warm_store.get_calibrations()

    # 4. Insights de segmento relevantes
    segment = detect_segment(product_idea)
    segment_insights = await warm_store.get_segment_memory(
        segment=segment, max_tokens=1000
    )

    # 5. Montar contexto com budget de 4.000 tokens
    # Análogo ao soft-trim do OpenClaw
    return assemble_context_within_budget(
        brand_context=brand_context,              # 500 tokens (sempre completo)
        historical_patterns=historical_patterns,  # até 1.500 tokens
        score_calibrations=score_calibrations,    # até 500 tokens
        segment_insights=segment_insights,        # até 1.000 tokens
        budget=4000
    )
```

---

### Momento 2 — PÓS-EXECUÇÃO (Post-briefing Flush)
*O equivalente do PRE-COMPACTION FLUSH do OpenClaw. NUNCA pode ser skippado. Roda em transação atômica.*

```
1. LLM (Haiku) sintetiza o que vale lembrar
2. Escreve no Hot Store: archive do thread completo
3. Escreve no Warm Store: padrão embedado + insights de segmento
4. Escreve no Cold Store: entrada no log diário (briefings/YYYY-MM-DD.md)
```

---

### Momento 3 — PÓS-DECISÃO DO COMITÊ (Committee Memory Flush)
*O flush mais crítico. Disparado pelo polling do Basecamp. Usa transação atômica + WAL mode. NUNCA pode ser perdido.*

```
Se GO:
→ Marca como aprovado no Hot Store
→ Atualiza MEMORY.md com padrão de sucesso
→ Peso × 2.0 no ChromaDB para briefings aprovados

Se NO-GO:
→ Extrai motivos de rejeição
→ Cria padrão de rejeição no ChromaDB
→ Atualiza MEMORY.md com "PADRÕES DE REJEIÇÃO A EVITAR"

Após 5 decisões: recalibra BVS Preditivo (Bayesian updating)
Archive final do briefing completo em JSONL
```

---

### Momento 4 — MANUTENÇÃO PERIÓDICA (cron semanal)
*Análogo ao session maintenance do OpenClaw.*

```
1. AGING:      soft-trim para insights > 90 dias
               hard-clear para insights > 1 ano
2. COMPACTION: consolida logs diários com > 10 entradas por segmento
3. PRUNING:    remove duplicatas semânticas no ChromaDB
4. BACKUP:     git commit do Cold Store
```

---

## Como o Agente 8 se Liga aos Outros 7

```
Agente 1 recebe (pré-execução):
• Padrões históricos de briefings similares (aprovados/rejeitados)
• Alertas de padrão de rejeição detectado
• Calibrações de IAM por tipo de ideia

Agente 2 recebe (pré-execução):
• Histórico de BVS Preditivo vs Real
• Ajustes de calibração por Onda
• Gaps de portfólio identificados historicamente

Agente 4 recebe (pré-execução):
• Insights de segmento consolidados (não reanálisa o já sabido)
• Tendências emergentes de períodos recentes
• Flag de staleness (> 90 dias = reanálise recomendada)

Agente 5 recebe (pré-execução):
• Baselines de RICE por segmento
• Confidence baselines (com/sem dados ABSA)
• Effort baselines por tipo de formulação
```

---

## MIP — Memory Integration Protocol (Extensibilidade)

Qualquer novo agente implementa 3 métodos. O Agente 8 os descobre automaticamente — sem necessidade de modificá-lo.

```python
class MemoryIntegrationProtocol:
    @abstractmethod
    def get_memory_read_request(self, state) -> MemoryReadRequest:
        """O que este agente precisa ler antes de executar"""
        pass

    @abstractmethod
    def get_memory_write_contribution(self, state, output) -> MemoryWriteContribution:
        """O que este agente escreve após executar"""
        pass

    @abstractmethod
    def get_memory_collection_name(self) -> str:
        """Nome da coleção ChromaDB — ex: 'agent_9_pricing'"""
        pass

# EXEMPLO — Agente 9 de Precificação:
class PricingAgent(MemoryIntegrationProtocol):
    def get_memory_collection_name(self) -> str:
        return "agent_9_pricing"
```

---

## Schema SQL — Hot Store

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE briefing_threads (
    thread_id           TEXT PRIMARY KEY,
    product_idea        TEXT NOT NULL,
    pm_id               TEXT NOT NULL DEFAULT 'jay',
    segment             TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    current_status      TEXT NOT NULL DEFAULT 'running',
    -- running | awaiting_human | pending_committee |
    -- committee_go | committee_no_go | archived
    iam_score           REAL,
    bvs_preditivo       REAL,
    bvs_real            REAL,    -- preenchido 6 meses após lançamento
    rice_score          REAL,
    icb_score           REAL,
    committee_decision  TEXT,    -- 'GO' | 'NO-GO' | 'HOLD'
    committee_date      TIMESTAMP,
    committee_reasons   TEXT,    -- JSON array
    committee_notes     TEXT,
    memory_flush_done   BOOLEAN DEFAULT FALSE,
    memory_flush_at     TIMESTAMP,
    last_memory_read_at TIMESTAMP,
    langgraph_thread_id TEXT UNIQUE
);

CREATE TABLE score_calibrations (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    calibration_date         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    n_data_points            INTEGER NOT NULL,
    bvs_onda1_adjustment     REAL DEFAULT 0.0,
    bvs_onda2_adjustment     REAL DEFAULT 0.0,
    bvs_onda3_adjustment     REAL DEFAULT 0.0,
    bvs_total_adjustment     REAL DEFAULT 0.0,
    rice_confidence_baseline REAL DEFAULT 6.0,
    confidence_level         TEXT DEFAULT 'baixa'
);

CREATE TABLE memory_patterns (
    id               TEXT PRIMARY KEY,
    pattern_type     TEXT NOT NULL,  -- 'approval'|'rejection'|'segment_insight'
    segment          TEXT,
    description      TEXT NOT NULL,
    occurrences      INTEGER DEFAULT 1,
    confidence       TEXT DEFAULT 'baixa',
    first_seen_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active        BOOLEAN DEFAULT TRUE,
    source_thread_ids TEXT  -- JSON array
);
```

---

## Por que essa arquitetura funciona

| Necessidade | Solução |
|---|---|
| Memória calibrável (BVS Preditivo vs Real) | Hot Store + calibration engine |
| Memória estruturada por evento (Comitê) | Committee Memory Flush — transação ACID única (Hot + Warm no mesmo SQLite) |
| Memória semântica buscável | sqlite-vec (vetorial) + FTS5 (keyword) — busca híbrida |
| Memória partilhada entre agentes | Estado compartilhado via LangGraph |

**Stack completa — zero servidores, zero SaaS:**
```
novex-memory.db (único arquivo SQLite)
├── briefing_threads      ← Hot Store
├── score_calibrations    ← Hot Store
├── memory_patterns       ← Hot Store
├── chunks_vec            ← Warm Store vetorial (sqlite-vec)
├── chunks_fts            ← Warm Store keyword (FTS5 built-in)
└── embedding_cache       ← cache de vetores

Embedding: nomic-embed-text via Ollama (local, 768 dims, gratuito)
Upgrade path: LanceDB quando busca > 200ms (troca 1 arquivo, 0 agentes mudam)
```

Nem a memória nativa do Claude (opaca, gerenciada pela Anthropic) nem o OpenClaw sozinho (sem RAG, sem paralelismo) resolveriam essas 4 necessidades. A Memória Viva é a síntese necessária.
