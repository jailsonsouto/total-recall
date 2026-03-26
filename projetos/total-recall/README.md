# Total Recall

> Memória pesquisável para o Claude Code — recupere decisões, diagnósticos e código de sessões passadas em segundos, direto de dentro da conversa.

---

## O problema que todo usuário do Claude Code conhece

Você passou duas horas debugando um problema com o Claude. Encontraram a causa raiz, definiram a arquitetura, escolheram o banco de dados. Sessão encerrada.

Três dias depois: *"Por que não usamos pgvector mesmo?"*

A resposta está no disco — em algum JSONL em `~/.claude/projects/`. Opaco. Inacessível. Perdido para todos os efeitos práticos.

O `auto-memory` nativo do Claude Code seleciona o que *parece* relevante no momento e descarta o resto. Decisões implícitas, raciocínios exploratórios, diagnósticos de causa-raiz — exatamente o tipo de conhecimento que você mais vai precisar depois.

**Total Recall não seleciona. Indexa tudo. E torna recuperável.**

---

## O que é

Um sistema local de busca semântica sobre o histórico completo de sessões do Claude Code. Roda inteiramente na sua máquina — sem API externa, sem transmissão de dados, sem custos de uso.

Você escreve uma pergunta em linguagem natural (ou um termo técnico, ou um typo) e o sistema encontra os trechos relevantes em qualquer sessão, de qualquer projeto, de qualquer data.

A busca funciona de dois lugares:

- **Terminal** — `total-recall search "sua query"`
- **Dentro do Claude Code** — `/recall sua query` (sem sair da conversa)

---

## Capacidades

### Busca que entende linguagem humana — typos incluídos

Você não precisa lembrar o termo exato. O sistema corrige:

| O que você digita | O que ele encontra |
|---|---|
| `sqilte vec` | `sqlite-vec` |
| `nuvex` | `novex` |
| `session id` | `session_id` |
| `vc decidiu` | `você decidiu` |
| `chromdb` | `chromadb` |

Três camadas de tolerância léxica: normalização de separadores, expansão de abreviações PT-BR (38 entradas) e fuzzy matching via rapidfuzz. Cada camada é independente — se uma não resolve, a próxima tenta.

### Busca semântica + keywords — o melhor dos dois mundos

Combina embedding vetorial com ranking BM25. O vetor captura significado e paráfrases; o BM25 garante que nomes técnicos e siglas exatas sejam encontrados com precisão. Nenhum dos dois sozinho é suficiente.

O sistema detecta automaticamente o tipo de query e ajusta os pesos antes de buscar:

| Tipo de query | Exemplo | Pesos |
|---|---|---|
| Semântica / descritiva | `"por que não usamos pgvector"` | 70% vetor / 30% FTS5 |
| Técnica / específica | `"PLN"`, `"BERTimbau"`, `"MLEGCN"` | 25% vetor / 75% FTS5 |

Queries com palavras de contexto (`"como"`, `"por que"`, `"decidimos"`) → modo híbrido. Queries curtas com termos técnicos, acrônimos ou nomes de modelos → modo FTS5-dominante. O modo ativo aparece em `--format json` como `search_mode`.

```bash
# Query semântica aberta — encontra pelo conceito
total-recall search "por que não usamos pgvector"

# Nome técnico exato — encontra pela sigla
total-recall search "WAL checkpoint SQLite"

# Cross-lingual — query em inglês, conteúdo em português
total-recall search "what did we decide about vector storage"
```

### Decisões arquiteturais não envelhecem

Sessões recentes têm boost natural (meia-vida de 30 dias). A exceção são decisões: chunks com linguagem arquitetural — *"decidimos"*, *"ao invés de"*, *"trade-off"*, *"schema"* — são tratados como atemporais. Uma decisão de seis meses atrás aparece com o mesmo peso de ontem.

### Clippings — resultados salvos como Markdown

Encontrou algo valioso? Salva com um flag:

```bash
total-recall search "lancedb decisão" --format context --output -auto-
# → ~/.total-recall/clips/2026-03-26_lancedb-decisao.md
```

Markdown pronto para reler, citar ou compartilhar.

### `/recall` — memória acessível de dentro do Claude Code

Sem sair da conversa. Sem copiar e colar. O Claude recebe os trechos relevantes diretamente no contexto e responde com base neles.

```
/recall por que escolhemos sqlite-vec?
/recall diagnóstico do bug de session_id
/recall arquitetura de memória --clip
```

---

## Instalação

**Pré-requisitos:** Python 3.9+ e [Ollama](https://ollama.com) instalado e rodando.

```bash
# 1. Clone o repositório
git clone https://github.com/jailsonsouto/total-recall.git
cd total-recall

# 2. Ambiente virtual
python3.12 -m venv .venv
source .venv/bin/activate      # macOS/Linux
# .venv\Scripts\activate       # Windows

# 3. Instalar
pip install -e .

# 4. Baixar o modelo de embedding
ollama pull qwen3-embedding:4b

# 5. Inicializar e indexar
total-recall init
total-recall index
```

Pronto. Suas sessões do Claude Code estão indexadas e pesquisáveis.

**Acesso global** (sem ativar o venv manualmente em cada terminal):

```bash
cp .local-bin/total-recall ~/.local/bin/total-recall
chmod +x ~/.local/bin/total-recall
```

---

## Uso

### Indexação

```bash
total-recall index                    # Incremental — só sessões novas ou modificadas
total-recall index --full             # Reindexação completa (necessário ao trocar modelo)
total-recall index --subagents        # Inclui sessões de subagentes (excluídas por padrão)
```

### Busca no terminal

```bash
# Busca básica
total-recall search "como decidimos sobre a arquitetura de memória"

# Mais resultados
total-recall search "temporal decay" -n 10

# Filtrar por sessão específica (aceita prefixo do UUID)
total-recall search "diagnóstico bug" --session 9739fab2

# Saída estruturada para injeção manual no Claude
total-recall search "sqlite WAL" --format context

# Salvar como clipping com nome automático
total-recall search "lancedb decisão" --format context --output -auto-
# → ~/.total-recall/clips/2026-03-26_lancedb-decisao.md

# Salvar com nome específico
total-recall search "lancedb decisão" --format context --output minha-pesquisa.md

# Saída JSON para processamento externo
total-recall search "fuzzy matching" --format json
```

### Skill `/recall` dentro do Claude Code

Após `total-recall init`, a skill `/recall` fica disponível em qualquer sessão:

| Sintaxe | Comportamento |
|---|---|
| `/recall <query>` | Busca e apresenta resultados (padrão: 8) |
| `/recall <query> --limit 15` | Mais resultados |
| `/recall <query> --session abc123` | Filtra por sessão |
| `/recall <query> --clip` | Busca + salva clipping automaticamente |
| `/recall <query> --session abc123 --clip` | Combinado |

O Claude analisa os trechos recuperados, sintetiza e responde — com citação de sessão, data e fonte.

### Sessões e exportação

```bash
# Listar sessões indexadas
total-recall sessions

# Filtrar por projeto
total-recall sessions --project AGENTES

# Exportar sessão completa para Markdown
total-recall export 31c6d284
# → ~/.total-recall/exports/31c6d284.md

# Estado do sistema
total-recall status
```

---

## Como funciona

### Pipeline de indexação

```
~/.claude/projects/**/*.jsonl
         │
         ▼ total-recall index
         │
         ├─ Parser JSONL → exchanges + blocos seletivos (thinking, tool_result)
         ├─ Chunking exchange-based com overlap de 200 chars
         ├─ Embedding qwen3-embedding:4b (1024 dims, instruction-aware)
         └─ SQLite WAL
                ├─ chunks_vec  (sqlite-vec — busca vetorial cosine)
                └─ chunks_fts  (FTS5/BM25 — busca por keywords)
```

### Pipeline de busca

```
Query do usuário
         │
         ▼ Tolerância léxica (pré-processamento)
         │   ├─ Normalização: sqlite-vec = sqlite vec = sqlite_vec
         │   ├─ Abreviações PT-BR: vc → você, pq → porque (38 entradas)
         │   └─ Fuzzy matching: sqilte → sqlite, nuvex → novex
         │
         ▼ Classificação de query (V03)
         │   ├─ Stop words detectadas → híbrido 70% vetor / 30% FTS5
         │   └─ Query técnica/curta  → FTS5-dominante 25% / 75%
         │
         ▼ Busca híbrida
         │   ├─ Vetorial: similaridade semântica, cross-lingual
         │   └─ FTS5/BM25: termos exatos, siglas, acrônimos, identificadores
         │
         ▼ Scoring e re-ranking
             ├─ Temporal decay: meia-vida 30 dias (decisões são atemporais)
             └─ MMR (λ=0.7): diversidade — sem 5 resultados do mesmo parágrafo
```

### Decisões de design

**Exchange-based chunking** — a unidade semântica não é a mensagem, é o *exchange* (pergunta + resposta). A resposta isolada da pergunta que a motivou perde significado recuperável.

**Indexação seletiva de blocos internos** — `thinking` e `tool_result` são ruidosos. Só são indexados quando contêm marcadores de valor: `"decidimos"`, `"root cause"`, `"trade-off"`, `"ADR"`. Com peso reduzido (0.6–0.7) para não competir com conteúdo explícito.

**Fuzzy com heurística de doc count** — tokens com ≤ 10 documentos no vocabulário FTS5 são tratados como typos e passam pelo fuzzy. Palavras comuns (`"como"`, 182 docs) usam busca literal. Evita expansões ruidosas sem suprimir correções legítimas.

**Append-only indexing** — sessões que cresceram têm apenas os novos chunks adicionados. Reduz o custo de reindexação em 10–50x para sessões longas.

**Graceful degradation** — sem Ollama, o sistema opera em modo FTS5-only. Indexação continua, busca por keywords funciona. O modo híbrido é restaurado automaticamente quando o Ollama voltar.

**Piso de confiança vetorial** — resultados recuperados exclusivamente pelo motor vetorial (sem match FTS5) são descartados se o score estiver abaixo de 0.42. Quando um termo não existe no corpus, a busca vetorial devolve os "menos distantes" do espaço — que podem ter distância de cosseno ~0.7 (similaridade ~0.29). Prefere-se "nenhum resultado" a ruído com aparência de sinal. Resultados com contribuição FTS5 passam incondicionalmente — o match literal é prova de existência no corpus.

**Ponderação adaptativa por tipo de query** — antes de buscar, o sistema classifica a query em três etapas: (1) presença de stop words semânticas → modo híbrido 70/30; (2) query curta sem contexto descritivo (≤ 2 tokens significativos) → modo FTS5-dominante 25/75; (3) todos os tokens são termos técnicos (ALL-CAPS, acrônimos de 2–3 letras, nomes com prefixo maiúsculo como `BERTimbau`, ou raros no corpus) → modo FTS5-dominante. O desequilíbrio estrutural — FTS5 nunca pontua acima de 0.30 enquanto ruído vetorial frequentemente ultrapassa esse valor — torna o roteamento adaptativo necessário para queries técnicas.

---

## Stack

| Componente | Papel |
|---|---|
| **SQLite WAL** | Banco único, crash-safe, sem servidor |
| **sqlite-vec** | Busca vetorial por similaridade de cosseno |
| **FTS5** | Índice de texto completo com ranking BM25 |
| **qwen3-embedding:4b** | Embeddings multilíngues instruction-aware (MTEB score 69.45) |
| **Ollama** | Runtime local para o modelo de embedding |
| **rapidfuzz** | Fuzzy matching em C++ — ~0.2ms por token |
| **Click** | Interface de linha de comando |

**Por que qwen3-embedding:4b e não nomic-embed-text?**

O corpus é bilíngue (pt-BR + terminologia técnica em inglês). O `nomic-embed-text` funciona bem para inglês monolíngue; para recuperação *cross-lingual* genuína em um corpus técnico misto, o Qwen3 oferece ganho mensurável: MTEB multilingual 69.45 vs ~60. A dimensão foi fixada em 1024 (não 2560, o máximo do modelo) porque em sistema híbrido o vetor não carrega toda a carga semântica — 1024 é o equilíbrio correto entre qualidade e custo computacional.

---

## Configuração

Todos os parâmetros têm defaults razoáveis. Sobrescreva via variáveis de ambiente quando necessário:

```bash
TOTAL_RECALL_DATA=~/.total-recall           # Diretório de dados
TOTAL_RECALL_SESSIONS=~/.claude/projects    # Raiz dos JSONLs
TOTAL_RECALL_EMBED_PROVIDER=ollama          # ollama | openai
TOTAL_RECALL_OLLAMA_MODEL=qwen3-embedding:4b
TOTAL_RECALL_EMBEDDING_DIMENSIONS=1024      # 512–2560; 1024 é o ponto ideal
TOTAL_RECALL_EMBED_USE_QUERY_INSTRUCTION=true
TOTAL_RECALL_FUZZY_THRESHOLD=0.70           # Similaridade mínima para fuzzy
TOTAL_RECALL_FUZZY_MAX_EXPANSIONS=5         # Máximo de variantes por token
OPENAI_API_KEY=...                          # Apenas se provider=openai
```

---

## Performance e escalabilidade

Projetado para uso individual — centenas a alguns milhares de sessões.

| Métrica | Valor |
|---|---|
| Busca P50 | ~260ms |
| Busca P95 | ~270ms |
| Fuzzy matching | ~0.2ms por token |
| Reindexação incremental | <1s para sessões que cresceram |
| Armazenamento por chunk | ~4 KB (1024 dims, float32) |
| Limite prático | ~100k chunks antes de precisar otimizar |

Para corpora maiores: redução de dimensão para 512 (Qwen3 suporta truncagem L2 sem degradação significativa) antes de considerar backends alternativos.

---

## Estrutura do repositório

```
total-recall/
├── src/total_recall/
│   ├── config.py             # Constantes e variáveis de ambiente
│   ├── database.py           # Schema SQLite, WAL, sqlite-vec
│   ├── embeddings.py         # OllamaEmbedProvider, OpenAIEmbedProvider
│   ├── models.py             # SessionInfo, Chunk, SearchResult, RecallContext
│   ├── vector_store.py       # Busca híbrida + tolerância léxica
│   ├── session_parser.py     # Parser JSONL → exchanges + blocos seletivos
│   ├── session_discovery.py  # Varredura ~/.claude/projects/, delta SHA-256
│   ├── indexer.py            # Orquestração: discover → parse → embed → store
│   ├── recall_engine.py      # Temporal decay + role weights + MMR
│   ├── cold_export.py        # Exportação de sessão para Markdown
│   └── cli.py                # Interface Click
├── skill/
│   └── recall.md             # Definição da skill /recall
├── tests/
│   └── test_search.py        # Suite: fuzzy, highlighting, benchmark P95
├── docs/
│   ├── GUIA-USUARIO.md       # Referência completa de sintaxe e exemplos
│   ├── exemplos-clipping/    # Clippings reais do desenvolvimento
│   └── HANDOFF-*.md          # Decisões arquiteturais documentadas
└── APRENDIZADOS.md           # Registro técnico por sessão de desenvolvimento
```

**Runtime** (criado por `total-recall init`):

```
~/.total-recall/
├── total-recall.db     # SQLite único — sessions, chunks, vetores, FTS, cache
├── exports/            # Sessões exportadas em Markdown
└── clips/              # Clippings de busca
```

---

## Referências

O design converge com a arquitetura do [OpenClaw](https://openclawlab.com/en/docs/concepts/memory/) — busca híbrida vetor+BM25, MMR, temporal decay, sqlite-vec — que serviu como referência de validação. A implementação é independente: Python, específica para sessões do Claude Code, com extensões originais: exchange-based chunking, indexação seletiva de blocos internos, decay com exceção para decisões, role weights e tolerância léxica multicamada. Nenhum código foi derivado do OpenClaw.

---

*Projeto independente. Não tem vínculo com o Memória Viva.*
