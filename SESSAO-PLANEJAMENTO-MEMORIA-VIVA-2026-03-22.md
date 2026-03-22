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

Ao escolher entre LanceDB, SQLite, ChromaDB, Pinecone ou Milvus, fico travado no vendor? Os embeddings não migram para outros bancos de concorrentes, certo? Como isso afetaria o futuro do meu agente de memória e o framework de uma maneira geral? Quero respostas longas, explicativas e professorais. Faz uma explicação contextualizada de tudo que envolve a "memória viva". Coloque no contexto do meu processo de discovery, ideação e briefing.

---

### 🤖 Claude

*(Aula completa — 9 partes)*

---

#### Parte 1 — A Anatomia de um Embedding

Um embedding é literalmente uma lista de números:

```
"sérum de transição capilar com claim de 48h"
         │
         ▼
  Modelo de Embedding (text-embedding-3-small)
         │
         ▼
[0.023, -0.412, 0.891, 0.034, ..., 0.087]  ← 1.536 números decimais
```

O banco de vetores **só guarda esses números e os procura eficientemente**. É um bucket de floats com capacidade de busca. Nada mais.

---

#### Parte 2 — Onde o Lock-in Realmente Vive

```
LOCK-IN REAL → MODELO DE EMBEDDING (quem gera os vetores)

  OpenAI text-embedding-3-small  → 1.536 dimensões
  Google gemini-embedding-001    →   768 dimensões
  nomic-embed-text (local)       →   768 dimensões

  REGRA DE OURO: todos os vetores no banco DEVEM ser do MESMO modelo.
  Trocar o modelo = re-embedar tudo do zero.

PORTÁVEL → BANCO DE VETORES (onde os números ficam guardados)

  SQLite | LanceDB | ChromaDB | Pinecone | Milvus

  Migração: export floats → import floats. 30 linhas de Python.
  Os vetores viajam livremente entre qualquer desses bancos.
```

---

#### Parte 3 — A Pilha Completa (4 Camadas)

```
╔══════════════════════════════════════════════════════╗
║  CAMADA 1 — MODELO DE EMBEDDING    (LOCK-IN REAL)   ║
║  Traduz texto → números. Trocar = re-embedar tudo.  ║
╠══════════════════════════════════════════════════════╣
║  CAMADA 2 — STORE DE VETORES       (PORTÁVEL)       ║
║  Guarda floats e busca por proximidade.             ║
╠══════════════════════════════════════════════════════╣
║  CAMADA 3 — ÍNDICE DE BUSCA        (PERFORMANCE)    ║
║  Flat O(n) | HNSW | IVF-PQ                         ║
╠══════════════════════════════════════════════════════╣
║  CAMADA 4 — INTERFACE DE QUERY     (API/CLIENT)     ║
║  Diferente entre bancos — 1-2 arquivos de código.  ║
╚══════════════════════════════════════════════════════╝
```

---

#### Parte 4 — Os 5 Candidatos, Honestamente

| | SQLite vec | LanceDB | ChromaDB | Pinecone | Milvus |
|---|---|---|---|---|---|
| Onde roda | Arquivo local | Arquivo local | Local ou server | CLOUD ONLY (SaaS) | Docker obrigatório |
| Busca | O(n) flat | IVF-PQ (rápida) | HNSW (rápida) | HNSW/cloud | IVF-PQ/HNSW |
| FTS5 híbrido | SIM nativo | Não (manual) | Não (manual) | Não (pago extra) | Não (manual) |
| Custo | Zero | Zero | Zero | $$$ | Zero (infra própria) |
| Seus dados | Na sua máquina | Na sua máquina | Na sua máquina | NA NUVEM DELES | Na sua máquina |
| Validado OpenClaw | SIM (built-in) | SIM (extensão) | Não | Não | Não |
| Adequado para | ~100k vetores | 100M+ vetores | ~1M vetores | Qualquer escala | Bilhões |

---

#### Parte 5 — O Risco Real do Pinecone para Este Caso

```
O que mora na Memória Viva:
• "claim de duração sem P&D" → REJEITADO
• "portfólio canibaliza transição capilar" → REJEITADO
• "BVS sistematicamente superestima 8% em Onda 1" → calibração
• Gaps de portfólio por segmento

= repositório estratégico de inteligência de produto da Embelleze

Com Pinecone: esses dados vivem em servidores da Pinecone Inc., EUA.
LGPD + confidencialidade competitiva: risco real.
```

---

#### Parte 6 — A Abstração que Torna Tudo Portável

```python
class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]: pass

class VectorStore(ABC):
    @abstractmethod
    def upsert(self, id: str, vector: list[float], metadata: dict): pass
    @abstractmethod
    def search(self, vector: list[float], n: int) -> list[SearchResult]: pass

# MVP: SQLite
class SQLiteVectorStore(VectorStore):
    def search(self, vector, n):
        return self.db.execute(
            "SELECT * FROM chunks_vec ORDER BY vec_cosine(embedding, ?) LIMIT ?",
            [json.dumps(vector), n]
        )

# Escala: LanceDB — ZERO mudança nos agentes
class LanceDBVectorStore(VectorStore):
    def search(self, vector, n):
        return self.table.search(vector).limit(n).to_list()

# O Agente 8 nunca vê qual store está em uso
class MemorySearchEngine:
    def __init__(self, embed: EmbeddingProvider, store: VectorStore):
        self.embed = embed
        self.store = store

    def search(self, query: str, n: int = 5) -> list[SearchResult]:
        vector = self.embed.embed(query)
        return self.store.search(vector, n)
```

Com isso:
- Trocar SQLite → LanceDB: 1 arquivo muda
- Trocar OpenAI → modelo local: 1 arquivo muda
- Todos os 7 agentes, MIP, Committee Flush: zero alterações

---

#### Parte 7 — O Risco para o Framework dos 7+1 Agentes

```
Cenário sem abstração:
OpenAI muda preço de text-embedding-3-small em 2028
→ Pipeline de injeção de contexto quebra
→ Re-embedar 150 briefings acumulados
→ Validar qualidade da busca
→ Possível regressão no Agente 1

Cenário com abstração:
→ Troca EmbeddingProvider em 1 arquivo
→ Script de re-embedding: 30 minutos
→ Nenhum outro arquivo muda
```

---

#### Parte 8 — A Decisão Estratégica

```
DECISÃO 1 — MODELO DE EMBEDDING (lock-in real)

Recomendação: nomic-embed-text via Ollama (local, gratuito)
  ✓ Zero dependência de API externa
  ✓ Dados nunca saem da máquina
  ✓ 768 dimensões — adequado para o volume
  ✓ Re-embedar é um script, não uma crise

Alternativa: text-embedding-3-small (OpenAI)
  → Melhor qualidade semântica geral
  → Dependência de API + custo crescente

DECISÃO 2 — VECTOR STORE (portável)

MVP:    SQLite FTS5 + chunks_vec
        → Zero dependência nova (já existe no LangGraph)
        → Busca híbrida (vetorial + keyword) nativa
        → Adequado para os primeiros 3-5 anos

Escala: LanceDB
        → Quando? Busca SQLite > 200ms
        → Migração: 30 linhas, 0 mudanças nos agentes
        → Caminho validado pelo próprio OpenClaw

Nunca:  Pinecone (dados saem da empresa)
Nunca:  Milvus (infraestrutura desproporcional)
ChromaDB: tecnicamente ok, mas sem vantagem sobre SQLite+LanceDB
          para este projeto

DECISÃO 3 — ABSTRAÇÃO

EmbeddingProvider + VectorStore como interfaces.
Qualquer troca = modificar 1 arquivo + script de migração.
```

---

#### Parte 9 — O Futuro do Framework, Visualizado

```
HOJE (MVP — Estágio 2)
novex-memory.db (SQLite)
  ├── briefing_threads    (Hot Store)
  ├── score_calibrations  (Hot Store)
  ├── memory_patterns     (Hot Store)
  ├── chunks_fts   FTS5   (Warm Store — keyword)
  ├── chunks_vec   BLOB   (Warm Store — vetores)
  └── embedding_cache     (Warm Store — cache)

Embedding: nomic-embed-text (local, via Ollama)
Busca: O(n) — ok para primeiros ~2.000 vetores

EM 3 ANOS (Estágio 3-4, ~200 briefings acumulados)
Hot Store:  ainda SQLite
Warm Store: migra para LanceDB
Embedding:  nomic-embed-text OU text-embedding-3-small (mesma interface)

O QUE NÃO MUDA EM NENHUM CENÁRIO:
• Os 7 agentes
• O Agente 8 (MemorySearchEngine)
• O MIP
• O Committee Flush (WAL mode no SQLite)
• Os 4 Momentos
• A Cold Store (Markdown + Git)
```

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
