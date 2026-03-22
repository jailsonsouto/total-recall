# SESSÃO DE PLANEJAMENTO — Memória Viva
## Claude Code + Jay | 22 de Março de 2026
### Tema: Arquitetura, Stack, Portabilidade e Decisões Pre-Desenvolvimento

---

> **NOTA:** Transcrição integral da sessão de planejamento técnico da Memória Viva no Claude Code.
> Continua o trabalho iniciado na sessão anterior (ver `TRANSCRICAO-COMPLETA-CHAT-novex-agentes-memoria.md`).
> Esta sessão foca em decisões de stack e arquitetura antes do desenvolvimento.

---

## PARTE 1 — Estruturação Inicial do Projeto

---

### 👤 Jay

Agora que quero iniciar o planejamento do agente memória viva usando as conversas do arquivo: `TRANSCRICAO-COMPLETA-CHAT-novex-agentes-memoria.md`

---

### 🤖 Claude

Leu o arquivo de transcrição e o `projetos/memoria-viva/CLAUDE.md` (stub vazio). Identificou as seções relevantes:

- **PARTE 3** — PRD completo (linha 314)
- **Arquitetura Técnica** (linha 378) — 3 camadas, 4 momentos, schema SQL
- **PARTE 5 e 6** — Aulas sobre memória e aprendizado contínuo

**Estado atual:** `projetos/memoria-viva/` só tinha o `CLAUDE.md` stub.

**Proposta de estrutura:**

```
projetos/memoria-viva/
├── CLAUDE.md              ← atualizar com contexto completo
├── docs/
│   ├── PRD.md
│   ├── ARQUITETURA.md
│   ├── ADRs.md
│   └── GLOSSARIO.md
├── src/
└── ROADMAP.md
```

**Fases de implementação:**

| Fase | Estágio | Prazo | Entregável |
|---|---|---|---|
| MVP | Episódica | 4 semanas | Hot Store (SQLite) + flush básico |
| Fase 2 | Semântica | 3 meses | Warm Store (ChromaDB) + calibração Bayesiana |
| Fase 3 | Estratégica | 6+ meses | TD Learning + pattern detection |

---

### 👤 Jay

sim

---

### 🤖 Claude

Criou todos os arquivos extraindo conteúdo da transcrição:

- `projetos/memoria-viva/CLAUDE.md` — atualizado com contexto completo
- `projetos/memoria-viva/ROADMAP.md` — 4 estágios com milestones e checkboxes
- `projetos/memoria-viva/docs/PRD.md` — problemas, objetivos, requisitos MEM-001/007, métricas
- `projetos/memoria-viva/docs/ARQUITETURA.md` — 3 camadas, 4 momentos, schema SQL, MIP, código Python
- `projetos/memoria-viva/docs/ADRs.md` — 5 decisões com motivos e trade-offs
- `projetos/memoria-viva/docs/GLOSSARIO.md` — termos do domínio + referências técnicas

Commit: `bc5c641 — Estruturar planejamento completo do projeto Memória Viva`

---

## PARTE 2 — Análise da Arquitetura e Nano-claw

---

### 👤 Jay

Quero que leia e analise bem a arquitetura. Na conversa eu mencionei o nano-claw e pedi comparação com o memória-viva — isso foi entendido como um pedido de mudança? Não quero a memória dele. Quero o que há de bom no openclaw. Devo acertar alguma aresta no plano antes de seguir pro desenvolvimento?

---

### 🤖 Claude

**Sobre o nano-claw:** Nenhuma contaminação. A conversa usou o nano-claw exclusivamente como espelho do oposto — um sistema deliberadamente amnésico para deixar claro o que a Memória Viva não deve ser. Os docs refletem isso corretamente:
- `ARQUITETURA.md` — zero referência ao nano-claw
- `GLOSSARIO.md` — nano-claw listado como "stateless por escolha — o oposto do que queremos"
- Base técnica 100% OpenClaw

**3 Arestas críticas identificadas antes de codar:**

**Aresta 1 — Inconsistência MVP vs código do Momento 1**
O ROADMAP diz que o MVP usa só Hot Store + Cold Store. Mas o código Python do Momento 1 já chama `warm_store.semantic_search()` — que é ChromaDB, Estágio 3. No MVP o Warm Store não existe. O código do MVP não vai funcionar sem uma versão degradada.

**Aresta 2 — Committee Flush sem trigger definido**
O Momento 3 diz "disparado pelo polling do Basecamp" — mas não há especificação de como isso funciona. Webhook? Cron? Trigger manual? Afeta diretamente a confiabilidade do flush mais crítico do sistema.

**Aresta 3 — `bvs_real` não tem mecanismo de entrada**
O schema SQL tem `bvs_real REAL` preenchido "6 meses após o lançamento". Nenhuma definição de quem insere esse dado. É o coração da calibração Bayesiana do Estágio 3.

**Menores (resolvíveis durante o desenvolvimento):**
- `detect_segment()` — como detecta o segmento HNR?
- Inicialização dos embeddings do `BRAND_MEMORY.md`
- `pm_id DEFAULT 'jay'` — hard-coded intencional no MVP

---

## PARTE 3 — Sugestões para a Aresta 1

---

### 👤 Jay

Crie duas sugestões para endereçar a aresta 1.

---

### 🤖 Claude

**Sugestão A — Degradação explícita no Momento 1**

MVP implementa um `read_memory()` com dois caminhos: se ChromaDB não existe, cai no Cold Store direto.

```python
async def read_memory_for_execution(product_idea, pm_context):
    brand_context = cold_store.read("BRAND_MEMORY.md")
    pm_context    = cold_store.read("PM_CONTEXT.md")

    if warm_store.is_available():                    # Estágio 3+
        patterns = await warm_store.semantic_search(...)
        calibrations = await warm_store.get_calibrations()
        segment_insights = await warm_store.get_segment_memory(...)
    else:                                            # MVP
        patterns = cold_store.read("MEMORY.md")     # leitura linear
        calibrations = {}
        segment = detect_segment(product_idea)
        segment_insights = cold_store.read(f"segments/{segment}.md")

    return assemble_context_within_budget(...)
```

Vantagem: MVP mínimo, zero dependência nova.
Desvantagem: Com >20 padrões, `MEMORY.md` inteiro vai para o contexto sem ranking semântico.

---

**Sugestão B — Warm Store no MVP com SQLite FTS5**

Implementar versão leve do Warm Store dentro do próprio SQLite usando FTS5. A interface `warm_store.semantic_search()` existe desde o dia 1.

```python
# MVP: busca por texto (FTS5)
async def semantic_search(query, collections, n_results, max_tokens):
    return sqlite.fts5_search(query, table="memory_patterns", limit=n_results)

# Estágio 3: troca só o corpo — interface idêntica
async def semantic_search(query, collections, n_results, max_tokens):
    embedding = embed(query)
    return chromadb.query(embedding, n_results=n_results)
```

```sql
CREATE VIRTUAL TABLE memory_patterns_fts
    USING fts5(description, segment, content=memory_patterns);
```

Vantagem: interface estável desde o MVP, zero refatoração no Estágio 3.
Desvantagem: FTS5 não é semântico — não reconhece similaridade conceitual.

**Quadro comparativo:**

| | Sugestão A | Sugestão B |
|---|---|---|
| Velocidade para o MVP | Mais rápida | +1-2h |
| Qualidade da busca no MVP | Baixa (leitura linear) | Média (FTS5) |
| Refatoração no Estágio 3 | Alta | Baixa |

---

## PARTE 4 — O Mecanismo Real do OpenClaw

---

### 👤 Jay

Bem, eu não gostaria de implementar algo e depois ter que refazer. A busca do openclaw é uma mistura de semântica e vetorial (ele não usa chroma), certo? Pode ver o código em https://github.com/openclaw/openclaw e me dizer se a sugestão A ou B seguem o brilhante mecanismo de memória do openclaw? No contexto macro, qual seria a melhor solução no momento observando o projeto como um todo (outros agentes do framework). Não quero desenvolver nada isolado que não traga benefício para o projeto.

---

### 🤖 Claude

*[Agente explorador leu o código-fonte do repositório openclaw/openclaw]*

**Descoberta crítica: OpenClaw não usa ChromaDB nem Pinecone.**

O que o OpenClaw realmente usa:

```sql
-- Tudo dentro do próprio SQLite:
CREATE TABLE chunks_vec (
  id PRIMARY KEY,
  embedding BLOB,       -- vetor armazenado como blob
  source TEXT, path TEXT, lineNumbers JSONL
)
CREATE VIRTUAL TABLE chunks_fts USING fts5(...)  -- busca keyword BM25
CREATE TABLE embedding_cache (...)               -- cache local
```

**Arquivos relevantes:**
- `/src/memory/hybrid.ts` — merge de vetorial + keyword com MMR e Temporal Decay
- `/src/memory/manager.ts` — gestor principal
- `/src/memory/memory-schema.ts` — schema SQLite
- `/extensions/memory-lancedb/index.ts` — extensão LanceDB (upgrade opcional)

**Fórmula de busca híbrida:**
```
finalScore = vectorWeight × vectorScore + textWeight × textScore
+ MMR (diversidade) + TemporalDecay (half-life 30 dias)
```

**Nenhuma das duas sugestões segue o OpenClaw:**

| | Sugestão A | Sugestão B | OpenClaw |
|---|---|---|---|
| MVP store | Cold Store | SQLite FTS5 | SQLite FTS5 + vec BLOB |
| Upgrade | Adiciona ChromaDB | Troca por ChromaDB | SQLite permanente, add embedding |
| Vector DB | Nenhum | ChromaDB | SQLite nativo |

**Sugestão C — SQLite nativo como store permanente (seguindo o OpenClaw):**

```
MVP:     SQLite FTS5 (chunks_fts)        → busca keyword, zero config
Fase 2:  SQLite FTS5 + chunks_vec        → add embedding provider, mesmo DB
Produção: SQLite (idem)                  → não migra para lugar nenhum
```

**Para o framework de 7+1 agentes:**
- Hot Store (LangGraph SqliteSaver) + Warm Store (memória semântica) no mesmo arquivo `.db`
- Nenhuma infraestrutura nova — SQLite já existe por causa do LangGraph
- Novos agentes via MIP plugam no mesmo DB
- ADR-001 (ChromaDB/Pinecone) cai por terra

---

## PARTE 5 — Sugestão C vs. as Aulas da Sessão Anterior + SQLite Scalability

---

### 👤 Jay

Quero que você tenha atenção ao documento inicial da minha conversa com o Chat do Claude. Lá tem a sessão AULA 5 — Por Que Nenhuma Delas Serve Sozinha para o Seu Workflow. Se eu aceitar a sua atualização, vou perder algum aspecto positivo listado lá na "aula sobre memória"? Uma dúvida sobre escalar. O SQLite é capaz de lidar com o crescimento da base de dados e do número de usuários ao longo dos anos? Algum "filhote de openclaw" fez a substituição do DB?

---

### 🤖 Claude

**1. Você perde algo da AULA 5 com a Sugestão C?**

Não. As 4 necessidades da AULA 5:

| Necessidade | Implementação original | Com Sugestão C | Capacidade perdida? |
|---|---|---|---|
| N1 — Calibrável | Hot Store SQLite | Hot Store SQLite | Nenhuma |
| N2 — Por evento | WAL mode | WAL mode | Nenhuma |
| N3 — Semântica buscável | "ChromaDB com embeddings" | SQLite `chunks_vec` + embeddings | **Nenhuma** |
| N4 — Partilhada | LangGraph | LangGraph | Nenhuma |

A N3 muda apenas na implementação, não na capacidade. A "semântica" está nos embeddings (modelo), não no banco. A síntese da AULA 3 da segunda sessão:

```
Few-Shot In-Context Learning  → preservado
        +
  RAG (busca semântica)        → preservado (SQLite ≡ ChromaDB para RAG)
        +
Bayesian Parameter Updating   → preservado
        =
     MEMÓRIA VIVA
```

O que a AULA 6 listou como "Busca semântica: Sim (ChromaDB)" era um detalhe de implementação assumido na sessão original — e estava incorreto em relação ao próprio OpenClaw de referência.

**2. SQLite escala ao longo dos anos?**

Para este volume: sim, com muita folga.

```
50 briefings/ano × 10 chunks = 500 vetores/ano
Em 5 anos  =  2.500 vetores
Em 10 anos =  5.000 vetores

Busca O(n) em 5.000 vetores: < 5ms
Limite de desconforto: ~100k-500k vetores
```

O único cenário que estressaria o SQLite: múltiplos PMs escrevendo simultaneamente (1 writer por vez em SQLite). Para um sistema de briefing sequencial por uma única empresa: não é um problema real.

**3. Algum "filhote" do OpenClaw substituiu o DB?**

Sim — e quem fez foi **o próprio OpenClaw**: `/extensions/memory-lancedb/index.ts`.

LanceDB:
- Arquivo local (sem servidor), como SQLite — mesma filosofia "local first"
- Columnar (Apache Arrow) com índices nativos IVF-PQ → busca O(log n)
- Construído especificamente para vetores em escala

Caminho validado pelo OpenClaw:
```
SQLite built-in (MVP, escala pequena)
         ↓
LanceDB extension (quando escala exigir)
```

ChromaDB não aparece em lugar nenhum no OpenClaw.

---

## PARTE 6 — Aula sobre Portabilidade de Vetores e Vendor Lock-in

---

### 👤 Jay

Ao escolher entre LanceDB, SQLite, ChromaDB, Pinecone ou Milvus, fico travado no vendor? Os embeddings não migram para outros bancos de concorrentes, certo? Como isso afetaria o futuro do meu agente de memória e o framework de uma maneira geral? Quero respostas longas, explicativas e professorais. Faz uma explicação contextualizada de tudo que envolve a "memória viva". Coloque no contexto do meu processo de discovery, ideação e briefing. Claude, seja um professor universitário nível ivy league nesse momento. Seja didático, faça esquemas, gráficos ou use qualquer subterfúgio para tornar claro esse processo.

---

### 🤖 Claude

# Uma Aula sobre Portabilidade de Memória Vetorial
## O que você precisa saber antes de construir a Memória Viva

---

#### PARTE 1 — A Anatomia de um Embedding

Antes de falar de bancos, precisamos entender o que você está guardando.

Quando o Agente 8 processa "sérum de transição capilar com claim de 48h", ele não salva a frase. Ele salva isso:

```
"sérum de transição capilar com claim de 48h"
         │
         ▼
  Modelo de Embedding
  (text-embedding-3-small)
         │
         ▼
[0.023, -0.412, 0.891, 0.034, -0.201, ..., 0.087]
         └────────────────────────────────────┘
                    1.536 números decimais
              = 1 vetor no espaço semântico
```

Esse vetor é a **representação matemática do significado** da frase. Duas ideias parecidas no mundo real ficam próximas nesse espaço de 1.536 dimensões — é isso que permite a busca semântica.

O banco de vetores (SQLite, LanceDB, ChromaDB, Pinecone) **só guarda esses números e os procura eficientemente**. É um bucket de floats com capacidade de busca. Nada mais.

Esse ponto é crítico para entender o vendor lock-in.

---

#### PARTE 2 — Onde o Lock-in Realmente Vive

A maioria das pessoas pensa que o lock-in está no banco. **Está errado.** O lock-in está no **modelo de embedding**.

```
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   MODELO DE EMBEDDING          ← LOCK-IN REAL               ║
║   (quem gera os vetores)                                     ║
║                                                              ║
║   OpenAI text-embedding-3-small  → 1.536 dimensões          ║
║   Google gemini-embedding-001    →   768 dimensões          ║
║   Voyage voyage-4-large          → 1.024 dimensões          ║
║   nomic-embed-text (local)       →   768 dimensões          ║
║                                                              ║
║   REGRA DE OURO:                                             ║
║   Todos os vetores no banco DEVEM ser do MESMO               ║
║   modelo. Vetores de modelos diferentes são                  ║
║   matematicamente incomparáveis.                             ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   BANCO DE VETORES              ← PORTÁVEL                   ║
║   (onde os números ficam guardados)                          ║
║                                                              ║
║   SQLite | LanceDB | ChromaDB | Pinecone | Milvus            ║
║                                                              ║
║   Os números viajam livremente entre qualquer                ║
║   desses bancos. É só exportar e importar.                   ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

**Por que o modelo é o lock-in?**

Imagine que você passou um ano gerando embeddings com `text-embedding-3-small` da OpenAI. Acumulou 50 briefings, cada um com 8 chunks = 400 vetores armazenados, todos em 1.536 dimensões.

Agora a OpenAI muda sua política de preços. Você quer migrar para um modelo local gratuito. Problema: o modelo local gera vetores em 768 dimensões. Os 400 vetores antigos vivem em um espaço de 1.536 dimensões. **Você não pode comparar diretamente vetores de dimensões diferentes** — é como tentar medir distâncias em metros e pés sem converter. Você teria que re-embedar **todo** o banco do zero com o novo modelo.

**Mas mudar de SQLite para LanceDB?** Isso é uma exportação de arrays de floats. Trivial:

```python
# Migração SQLite → LanceDB em 10 linhas
rows = sqlite.execute("SELECT id, embedding, text, metadata FROM chunks_vec").fetchall()

lance_table = lancedb.create_table("briefing_patterns", data=[
    {"id": r.id, "vector": json.loads(r.embedding), "text": r.text}
    for r in rows
])
# Pronto. Todos os vetores migraram. Zero perda.
```

Os números são os mesmos. Só mudou a casinha onde moram.

---

#### PARTE 3 — A Pilha Completa (4 Camadas)

Para planejar sem se perder, visualize o sistema como 4 camadas independentes:

```
╔══════════════════════════════════════════════════════════════╗
║  CAMADA 1 — MODELO DE EMBEDDING           (LOCK-IN REAL)    ║
║                                                              ║
║  É o "dicionário" que traduz texto → números.               ║
║  Todos os vetores no banco DEVEM ter vindo do mesmo         ║
║  dicionário. Trocar o dicionário = re-embedar tudo.         ║
║                                                              ║
║  Opções:                                                     ║
║  • OpenAI text-embedding-3-small  — pago, 1.536 dims        ║
║  • Google gemini-embedding-001    — pago, 768 dims          ║
║  • nomic-embed-text (via Ollama)  — GRÁTIS, local, 768 dims ║
║  • all-MiniLM-L6-v2               — GRÁTIS, local, 384 dims ║
╠══════════════════════════════════════════════════════════════╣
║  CAMADA 2 — STORE DE VETORES              (PORTÁVEL)        ║
║                                                              ║
║  É o bucket que guarda os floats e busca por proximidade.   ║
║  Trocar de store = export + import. Vetores viajam.         ║
║                                                              ║
║  SQLite → LanceDB → ChromaDB → Pinecone → Milvus            ║
╠══════════════════════════════════════════════════════════════╣
║  CAMADA 3 — ÍNDICE DE BUSCA               (PERFORMANCE)     ║
║                                                              ║
║  É o algoritmo que acelera a busca.                         ║
║  Flat (força bruta, O(n)) | HNSW | IVF-PQ                  ║
║  Não afeta os dados — é um índice, como no SQL.             ║
╠══════════════════════════════════════════════════════════════╣
║  CAMADA 4 — INTERFACE DE QUERY            (API/CLIENT)      ║
║                                                              ║
║  É como você pergunta ao banco.                             ║
║  Python client | REST | gRPC                                ║
║  Diferente entre bancos — é a parte que você reescreve      ║
║  numa migração. Normalmente 1-2 arquivos de código.         ║
╚══════════════════════════════════════════════════════════════╝
```

---

#### PARTE 4 — Os 5 Candidatos, Honestamente

Agora que você entende a pilha, avalie cada banco pelo que ele realmente é:

| | SQLite vec | LanceDB | ChromaDB | Pinecone | Milvus |
|---|---|---|---|---|---|
| Onde roda | Arquivo .db local | Arquivo local | Local ou servidor | CLOUD ONLY (SaaS) | Servidor/Docker obrigatório |
| Busca vetorial | O(n) flat (lenta >100k) | IVF-PQ (rápida) | HNSW (rápida) | HNSW/cloud (rápida) | IVF-PQ / HNSW (rápida >1M vecs) |
| FTS5 híbrido | SIM nativo | Não (manual) | Não (manual) | Não (pago extra) | Não (manual) |
| Custo operacional | Zero | Zero | Zero local | $$$ | Zero (infra própria) |
| Seus dados ficam | Na sua máquina | Na sua máquina | Na sua máquina | NA NUVEM DELES | Na sua máquina |
| Validado OpenClaw | SIM (built-in) | SIM (extensão oficial) | Não | Não | Não |
| Adequado para | Até ~100k vetores | Até 100M+ vetores | Até 1M vetores | Qualquer escala | Bilhões de vetores |

---

#### PARTE 5 — O Risco Real de Pinecone e Milvus para o Seu Caso

Este ponto merece atenção especial antes de qualquer decisão.

**Pinecone — o risco que não parece risco:**

```
BRIEFING REJECTED — "claim de duração sem P&D"
BRIEFING REJECTED — "portfólio canibaliza transição capilar"
BRIEFING APPROVED — "hidratação foco em identidade, não resultado"
SCORE CALIBRATION — "BVS sistematicamente superestima 8% em Onda 1"

Isso é o que mora na Memória Viva.
Isso é o repositório estratégico de inteligência de produto da Embelleze.

Com Pinecone: esses dados vivem em servidores da Pinecone Inc., EUA.
LGPD, GDPR, confidencialidade competitiva: risco real.
Se a Pinecone mudar de preço, ser comprada, ou ter um breach: seu ativo
estratégico está exposto. Pinecone não tem opção "bring your own key"
para dados em repouso.
```

Milvus não tem o problema de privacidade (você hospeda), mas tem um problema diferente: **infraestrutura pesada** (precisa de Docker, Kubernetes para produção, equipe de Ops). É uma solução para 50 engenheiros gerenciando bilhões de vetores. Não para um sistema que terá 5.000 vetores em 10 anos.

---

#### PARTE 6 — A Abstração que Torna Tudo Portável

Esta é a resposta de engenharia para o seu medo de ficar travado. A solução não é escolher o banco "certo para sempre" — é **projetar o código para que o banco seja substituível em 2 arquivos**.

```python
# O padrão que elimina o lock-in de BANCO

class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        pass

class VectorStore(ABC):
    @abstractmethod
    def upsert(self, id: str, vector: list[float], metadata: dict): pass

    @abstractmethod
    def search(self, vector: list[float], n: int) -> list[SearchResult]: pass

# ─────────────────────────────────────────────
# MVP: tudo em SQLite (zero infraestrutura)
# ─────────────────────────────────────────────
class SQLiteVectorStore(VectorStore):
    def search(self, vector, n):
        return self.db.execute(
            "SELECT * FROM chunks_vec ORDER BY vec_cosine(embedding, ?) LIMIT ?",
            [json.dumps(vector), n]
        )

# ─────────────────────────────────────────────
# Escala: LanceDB (substitui SQLiteVectorStore)
# ZERO mudança nos agentes, no Agente 8, no MIP
# ─────────────────────────────────────────────
class LanceDBVectorStore(VectorStore):
    def search(self, vector, n):
        return self.table.search(vector).limit(n).to_list()

# ─────────────────────────────────────────────
# O Agente 8 nunca vê qual store está em uso
# ─────────────────────────────────────────────
class MemorySearchEngine:
    def __init__(self, embed: EmbeddingProvider, store: VectorStore):
        self.embed = embed
        self.store = store

    def search(self, query: str, n: int = 5) -> list[SearchResult]:
        vector = self.embed.embed(query)          # camada 1
        return self.store.search(vector, n)        # camada 2
```

Com isso:
- **Trocar SQLite → LanceDB**: instancia `LanceDBVectorStore` em vez de `SQLiteVectorStore`. Um arquivo muda.
- **Trocar OpenAI → modelo local**: instancia `NomicEmbedProvider` em vez de `OpenAIEmbedProvider`. Um arquivo muda.
- **Todos os 7 agentes, o MIP, o Committee Flush**: zero alterações.

---

#### PARTE 7 — O Risco Real para o Seu Framework (Os 7+1 Agentes)

Voltando ao projeto inteiro. O impacto de uma escolha errada de embedding model vai além do Agente 8:

```
HOJE: Jay submete "sérum de transição" via OpenClaw
      │
      ▼
Agente 8 (Memory Read)
  → embed("sérum de transição")    usando OpenAI text-embedding-3-small
  → busca vetores similares
  → injeta contexto nos Agentes 1, 2, 4, 5

      │
      ▼
Agentes 1, 2, 4, 5 recebem contexto relevante
      │
      ▼
Briefing gerado com inteligência acumulada

EM 2 ANOS: OpenAI muda preço ou descontinua text-embedding-3-small

Se o modelo foi escolhido SEM abstração:
→ Todo o pipeline de injeção de contexto quebra
→ Re-embedar 150 briefings acumulados do zero
→ Validar que a qualidade da busca se manteve
→ Possível regressão na qualidade do Agente 1

Se o modelo foi escolhido COM abstração:
→ Troca EmbeddingProvider em 1 arquivo
→ Script de re-embedding: 30 minutos de processamento
→ Nenhum outro arquivo muda
```

**A Memória Viva é a fundação de todos os outros agentes.** Qualquer instabilidade nela contamina os 7. Portanto o princípio de design é: **nenhum agente sabe qual embedding model ou qual vector store está em uso**.

---

#### PARTE 8 — A Decisão Estratégica

Com tudo isso, a resposta para o seu projeto:

```
DECISÃO 1 — MODELO DE EMBEDDING
(onde está o lock-in real)

Recomendação: nomic-embed-text via Ollama (local, gratuito)

Por quê:
✓ Zero dependência de API externa
✓ Dados nunca saem da máquina
✓ 768 dimensões — adequado para o volume do projeto
✓ Qualidade comparável a text-embedding-3-small para domínios específicos
✓ Se precisar melhorar: re-embedar é um script, não uma crise

Alternativa aceitável: text-embedding-3-small (OpenAI)
→ Melhor qualidade semântica geral
→ Dependência de API + custo crescente
→ Use SE o modelo local provar qualidade insuficiente

───────────────────────────────────────────────────────

DECISÃO 2 — VECTOR STORE
(portável, mas vale escolher bem)

MVP: SQLite chunks_vec + FTS5
→ Zero dependência nova (já existe por causa do LangGraph)
→ Busca híbrida (vetorial + keyword) nativa
→ Basta para os primeiros 3-5 anos de operação

Escala: LanceDB
→ Quando? Quando a busca SQLite ultrapassar 200ms
→ Migração: script de 30 linhas, 0 mudanças nos agentes
→ Mantém filosofia local-first do OpenClaw
→ O próprio OpenClaw já validou esse upgrade path

Nunca para este projeto: Pinecone (dados saem da empresa)
Nunca para este projeto: Milvus (infraestrutura desproporcional)
ChromaDB: tecnicamente ok, mas não oferece nada que SQLite+LanceDB
não ofereça — e adiciona uma dependência sem o histórico do OpenClaw

───────────────────────────────────────────────────────

DECISÃO 3 — A ABSTRAÇÃO
(o que elimina o medo de lock-in)

EmbeddingProvider + VectorStore como interfaces
implementadas em 2 arquivos separados.

Qualquer troca = modificar 1 arquivo + script de migração.
Zero impacto nos 7 agentes, no MIP, no Agente 8 em si.
```

---

#### PARTE 9 — O Futuro do Framework, Visualizado

```
HOJE (MVP — Estágio 2)
─────────────────────────────────────────────────
novex-memory.db (SQLite)
  ├── briefing_threads        ← Hot Store (LangGraph state)
  ├── score_calibrations      ← Hot Store
  ├── memory_patterns         ← Hot Store
  ├── chunks_vec              ← Warm Store (vetores)
  ├── chunks_fts (FTS5)       ← Warm Store (keyword)
  └── embedding_cache         ← Warm Store (cache)

Embedding: nomic-embed-text (local, via Ollama)
Busca: O(n) — ok para primeiros ~2.000 vetores

EM 3 ANOS (Estágio 3-4, ~200 briefings acumulados)
─────────────────────────────────────────────────
Hot Store: ainda SQLite (calibrações, threads, padrões)
Warm Store: migra para LanceDB
  → lance://novex-memory/briefing_patterns
  → lance://novex-memory/segment_insights
  Busca IVF-PQ: O(log n), suporta 100M vetores

Embedding: nomic-embed-text OU text-embedding-3-small
(mesma interface, troca transparente)

O QUE NÃO MUDA EM NENHUM CENÁRIO
─────────────────────────────────────────────────
• Os 7 agentes: nunca sabem qual store está em uso
• O Agente 8: interface idêntica (MemorySearchEngine)
• O MIP: novos agentes plugam na mesma interface
• O Committee Flush: WAL mode no SQLite Hot Store
• Os 4 Momentos: pré-execução, pós-briefing,
  pós-comitê, manutenção — independentes do store
• A Cold Store: Markdown + Git — não tem vector store
```

---

### Síntese Final

| Pergunta | Resposta |
|---|---|
| Vou ficar travado no banco de vetores? | Não. Vetores são floats portáveis. |
| Onde está o lock-in real? | No modelo de embedding. |
| Como eliminar esse lock-in? | Abstração + modelo local (nomic). |
| SQLite aguenta o crescimento? | Sim, para este volume, indefinidamente. |
| Qual o upgrade natural do SQLite? | LanceDB — validado pelo próprio OpenClaw. |
| Pinecone/Milvus fazem sentido? | Não para este projeto. Pinecone = dados fora da empresa. |
| O que protege os outros 7 agentes? | A interface EmbeddingProvider + VectorStore. |

A Memória Viva bem projetada não tem vendor lock-in — tem **model lock-in gerenciado** (nomic local elimina) e **store portável** (floats viajam). O risco real é arquitetural: se os agentes chamarem `chromadb.query()` diretamente em vez de chamarem `memory.search()`, qualquer troca futura vira uma refatoração global. A abstração é o investimento que protege os próximos anos.

Quer que eu atualize o `ARQUITETURA.md` com a pilha de abstração e o `ADR-001` com a decisão SQLite → LanceDB antes de seguirmos para o desenvolvimento?

---

## PARTE 7 — Salvando a Sessão

---

### 👤 Jay

Claude, salva todo o conteúdo do nosso chat num markdown na raiz do projeto local. Pode escolher um nome significativo para ele. Nesse meio tempo eu ainda estou ponderando por qual caminho ir. Quero o conteúdo completo dessa sessão (íntegro).

---

### 🤖 Claude

Criou: `SESSAO-PLANEJAMENTO-MEMORIA-VIVA-2026-03-22.md`
Commit: `104e213 — Salvar transcrição completa da sessão de planejamento da Memória Viva`

---

### 👤 Jay

O conteúdo diverge do terminal. Por exemplo: Síntese Final não aparece no SESSAO-PLANEJAMENTO-MEMORIA-VIVA-2026-03-22.md

---

### 🤖 Claude

Identificou as divergências: Partes 2, 3, 5 e 7 condensadas; Síntese Final completamente ausente. Corrigiu o arquivo com o conteúdo íntegro do terminal.

---

## SÍNTESE DAS DECISÕES DESTA SESSÃO

| Questão | Decisão |
|---|---|
| Nano-claw contaminou o plano? | Não. Base 100% OpenClaw. |
| ChromaDB como Warm Store? | Fora do plano. SQLite nativo (como OpenClaw). |
| Pinecone em produção? | Não. Dados estratégicos fora da empresa. |
| Milvus? | Não. Infraestrutura desproporcional. |
| Upgrade natural do SQLite? | LanceDB — validado pelo próprio OpenClaw. |
| Embedding model? | nomic-embed-text local (decisão pendente final). |
| Lock-in de banco? | Não existe — vetores são floats portáveis. |
| Lock-in real? | No embedding model. Resolvido com abstração + modelo local. |
| Abstração necessária? | EmbeddingProvider + VectorStore como interfaces. |
| Aresta 1 (MVP vs Momento 1)? | Sugestão C — SQLite com FTS5 desde o MVP. |
| Aresta 2 (trigger Committee Flush)? | **Pendente decisão de Jay.** |
| Aresta 3 (bvs_real)? | **Pendente decisão de Jay.** |

---

## PRÓXIMOS PASSOS (antes do desenvolvimento)

1. **Decidir** Aresta 2: como o Committee Flush recebe o sinal de decisão (Basecamp webhook? cron? manual?)
2. **Decidir** Aresta 3: quem insere o `bvs_real` e quando (manual via CLI? API de analytics?)
3. **Validar** modelo de embedding: nomic-embed-text (local) ou text-embedding-3-small (OpenAI)?
4. **Atualizar** `ARQUITETURA.md` e `ADR-001` com a decisão SQLite→LanceDB (substituindo ChromaDB/Pinecone)
5. **Implementar** MVP (Estágio 2 — Episódica)

---

*Sessão gerada em: 22 de Março de 2026*
*Claude Code + Jay (PM Novex/Embelleze)*
*Status: planejamento em andamento — desenvolvimento ainda não iniciado*
