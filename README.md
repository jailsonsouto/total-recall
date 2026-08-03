# Total Recall

Busca semântica sobre o histórico de sessões do Claude Code. Recupere decisões, diagnósticos e código de conversas passadas em segundos, direto do terminal ou de dentro da conversa.

---

## O problema que todo usuário do Claude Code conhece

Você passou duas horas debugando um problema com o Claude. Encontraram a causa raiz, definiram a arquitetura, escolheram o banco de dados. Sessão encerrada.

Três dias depois: *"Por que não usamos pgvector mesmo?"*

A resposta está no disco, em algum JSONL em `~/.claude/projects/`. Opaco. Inacessível. Perdido para todos os efeitos práticos.

O `auto-memory` nativo do Claude Code seleciona o que *parece* relevante no momento e descarta o resto. Decisões implícitas, raciocínios exploratórios, diagnósticos de causa-raiz: exatamente o tipo de conhecimento que você mais vai precisar depois.

**Total Recall não seleciona. Indexa tudo. E torna recuperável.**

---

## O que é

Um sistema local de busca semântica sobre o histórico completo de sessões do Claude Code. Roda inteiramente na sua máquina, sem API externa, sem transmissão de dados, sem custos de uso.

Você escreve uma pergunta em linguagem natural (ou um termo técnico, ou um typo) e o sistema encontra os trechos relevantes em qualquer sessão, de qualquer projeto, de qualquer data.

A busca funciona de dois lugares:

- **Terminal:** `total-recall search "sua query"`
- **Dentro do Claude Code:** `/recall sua query` (sem sair da conversa)

---

## Capacidades

### Busca que entende linguagem humana, typos incluídos

Você não precisa lembrar o termo exato. O sistema corrige:

| O que você digita | O que ele encontra |
|---|---|
| `sqilte vec` | `sqlite-vec` |
| `nuvex` | `novex` |
| `session id` | `session_id` |
| `vc decidiu` | `você decidiu` |
| `chromdb` | `chromadb` |

Três camadas de tolerância léxica: normalização de separadores, expansão de abreviações PT-BR (38 entradas) e fuzzy matching via rapidfuzz. Se uma camada não resolve, a próxima tenta.

### Busca semântica e por keywords trabalhando juntas

Combina embedding vetorial com ranking BM25. O vetor captura significado e paráfrases; o BM25 garante que nomes técnicos e siglas exatas sejam encontrados com precisão.

O sistema detecta automaticamente o tipo de query e ajusta os pesos antes de buscar:

| Tipo de query | Exemplo | Pesos |
|---|---|---|
| Semântica / descritiva | `"por que não usamos pgvector"` | 70% vetor / 30% FTS5 |
| Técnica / específica | `"PLN"`, `"BERTimbau"`, `"MLEGCN"` | 25% vetor / 75% FTS5 |

Queries com palavras de contexto (`"como"`, `"por que"`, `"decidimos"`) usam modo híbrido. Queries curtas com termos técnicos, acrônimos ou nomes de modelos usam modo FTS5-dominante. O modo ativo aparece em `--format json` como `search_mode`.

```bash
# Query semântica aberta
total-recall search "por que não usamos pgvector"

# Nome técnico exato
total-recall search "WAL checkpoint SQLite"

# Query em inglês, conteúdo em português
total-recall search "what did we decide about vector storage"
```

### Decisões arquiteturais não envelhecem

Sessões recentes têm boost natural (meia-vida de 30 dias). A exceção são decisões: chunks com linguagem arquitetural como *"decidimos"*, *"ao invés de"*, *"trade-off"*, *"schema"* são tratados como atemporais. Uma decisão de seis meses atrás aparece com o mesmo peso de ontem.

### Clippings: resultados salvos como Markdown

Encontrou algo valioso? Salva com um flag:

```bash
total-recall search "lancedb decisão" --format context --output -auto-
# → ~/.total-recall/clips/2026-03-26_lancedb-decisao.md
```

Markdown pronto para reler, citar ou compartilhar.

### `/recall` dentro do Claude Code

Sem sair da conversa, sem copiar e colar. O Claude recebe os trechos relevantes diretamente no contexto e responde com base neles.

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

**Indexação automática** (recomendado): configure dois hooks em `~/.claude/settings.json` para que o índice seja atualizado automaticamente ao abrir cada sessão e antes de compactações de contexto. Detalhes em [docs/GUIA-USUARIO.md](docs/GUIA-USUARIO.md#7-rotina-recomendada).

**Acesso global** (sem ativar o venv manualmente em cada terminal):

```bash
cp .local-bin/total-recall ~/.local/bin/total-recall
chmod +x ~/.local/bin/total-recall
```

---

## Uso

### Indexação

```bash
total-recall index                    # Incremental: só sessões novas ou modificadas
total-recall index --full             # Reindexação completa (necessário ao trocar modelo)
total-recall index --subagents        # Inclui sessões de subagentes (excluídas por padrão)
```

**Subagentes por padrão:** configure para não precisar de `--subagents` toda vez:

```bash
export TOTAL_RECALL_INDEX_SUBAGENTS=true
total-recall index  # já inclui subagentes automaticamente
```

**O que é indexado de subagentes:** apenas subagentes significativos. Excluídos automaticamente:
- Subagentes disparados pela skill `/recall` (eco de buscas/sínteses — ruído auto-contaminação)
- Subagentes capturados com `attributionSkill` em uma lista de skills ruidosas

Confirmado via análise empírica (APRENDIZADOS.md #52): quase metade dos subagentes do usuário típico vêm da `/recall`, tornando a filtragem essencial.

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

# Tabela com barra de cobertura por termo — qual termo bateu em qual resultado
total-recall search "ASTE ABSA" --format table
```

### `--format table`: cobertura por termo, não score decimal opaco

O score combinado (vetor + FTS5, pesos adaptativos) não é comparável entre buscas diferentes — 0.24 numa busca não significa a mesma coisa que 0.24 noutra (o motivo é técnico: modo `fts5_dominant` vs `hybrid` mudam a fórmula). `--format table` resolve isso mostrando, pra cada termo da sua busca, se ele bateu **literal** (`█`), só via **fuzzy/abreviação** (`▒`), ou **não apareceu** (`░`) — um selo verificável, não uma conta interna:

```
Termos: ①duckdb ②analista     █ literal · ▒ fuzzy/abrev · ░ ausente

#  Relevância          Fonte          Origem       Sessão                              Idade
─  ──────────────────  ─────────────  ───────────  ──────────────────────────────────  ─────
1  [█████|░░░░░] 100%  VECTOR + FTS5  CLAUDE-CODE  subagents · agent-a0                17d
    ┃ ...trecho com "duckdb" mas sem "analista"...
5  [█████|█████] 82%   FTS5           CODEX        vozes-da-comunidade-v04 · 019f7028  17d
    ┃ ...trecho com os dois termos juntos...
```

O `%` é relativo ao melhor resultado *desta busca* (topo = 100%) — comparável dentro da mesma lista, não entre buscas diferentes. Um resultado com os dois segmentos acesos (como o `[5]` acima) pode estar em posição inferior no ranking e ainda ser o match mais completo — a barra revela isso de cara, sem precisar ler o trecho.

### Skill `/recall` dentro do Claude Code

Após `total-recall init`, a skill `/recall` fica disponível em qualquer sessão:

| Sintaxe | Comportamento |
|---|---|
| `/recall <query>` | Busca e apresenta resultados (padrão: 8) |
| `/recall <query> --limit 15` | Mais resultados |
| `/recall <query> --session abc123` | Filtra por sessão |
| `/recall <query> --clip` | Busca e salva clipping automaticamente |
| `/recall <query> --session abc123 --clip` | Combinado |

O Claude analisa os trechos recuperados, sintetiza e responde com citação de sessão, data, fonte e origem (`[CLAUDE-CODE]`/`[CODEX]`).

### Busca cruzada com o total-recall-codex

Se o projeto irmão [total-recall-codex](https://github.com/jailsonsouto/total-recall-codex) (mesma ferramenta, para sessões do Codex) estiver instalado e indexado na mesma máquina, o Total Recall pode consultar as duas coleções sob demanda. **O padrão continua sendo só este banco** (`claude-code`) — rápido, sem abrir uma segunda conexão nem embedar a query duas vezes. Busca cruzada é opt-in:

```bash
# Padrão: só este banco (Claude Code CLI)
total-recall search "por que escolhemos sqlite-vec"

# Cruzada: funde os dois bancos por score
total-recall search "por que escolhemos sqlite-vec" --source both

# Só o banco irmão
total-recall search "por que escolhemos sqlite-vec" --source codex
```

Cada resultado é marcado com `[CLAUDE-CODE]` ou `[CODEX]` em todos os formatos de saída (`rich`, `context`, `pointers`, `json`) — sempre, mesmo quando a origem é o banco local, para não obrigar o leitor a inferir por ausência de marca.

Na skill `/recall`, peça a busca cruzada com frases dentro do próprio pedido:

```
/recall cruzada: diagnóstico do bug de session_id
/recall buscar-no-codex: decisão sobre o parser de turnos abortados
```

**Isolamento continua total no disco.** A leitura do banco irmão é sempre read-only (conexão SQLite `mode=ro`, bloqueada a nível de driver — não só por convenção do código); os dois bancos nunca se tocam fisicamente, a fusão acontece só em memória, na hora de apresentar o resultado. Funciona porque os dois projetos usam o mesmo modelo de embedding (`qwen3-embedding:4b`, 1024 dims) — os vetores são comparáveis entre bancos.

Se o banco irmão não existir nessa máquina, `--source both` avisa em stderr e segue só com o banco local (não quebra); `--source codex` sozinho, sem o banco irmão, retorna um erro claro em vez de silêncio.

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
         ▼ total-recall index [--subagents]
         │
         ├─ Discovery com fast-path (stat mtime vs SHA-256, 145 arquivos em 0.028s)
         │
         ├─ Parser JSONL → exchanges + blocos seletivos (thinking, tool_result)
         │   └─ Subagentes: isSidechain=true é normal (não descartado em arquivo de subagente)
         │
         ├─ Chunking exchange-based com overlap de 200 chars
         │
         ├─ Embedding batched qwen3-embedding:4b (1024 dims, instruction-aware)
         │   └─ Lotes de 24 textos reduzem ~1000ms/chunk → ~110-150ms/chunk
         │
         └─ SQLite WAL (timeout 60s para evitar lock contention de writers concorrentes)
                ├─ chunks_vec  (sqlite-vec: busca vetorial cosine)
                └─ chunks_fts  (FTS5/BM25: busca por keywords)
```

**Nota de concorrência:** embeddings são gerados via Ollama dentro da transação de escrita. Hooks `SessionStart` e `PreCompact` podem dispará-lo em paralelo. O timeout de 60 segundos evita "database is locked" quando duas sessões abrem perto uma da outra. Fix estrutural (separar embedding da transação) está no backlog.

### Pipeline de busca

```
Query do usuário
         │
         ▼ Tolerância léxica (pré-processamento)
         │   ├─ Normalização: sqlite-vec = sqlite vec = sqlite_vec
         │   ├─ Abreviações PT-BR: vc → você, pq → porque (38 entradas)
         │   └─ Fuzzy matching: sqilte → sqlite, nuvex → novex
         │
         ▼ Classificação de query
         │   ├─ Stop words detectadas → híbrido 70% vetor / 30% FTS5
         │   └─ Query técnica/curta  → FTS5-dominante 25% / 75%
         │
         ▼ Busca híbrida
         │   ├─ Vetorial: similaridade semântica, cross-lingual
         │   └─ FTS5/BM25: termos exatos, siglas, acrônimos, identificadores
         │
         ▼ Scoring e re-ranking
             ├─ Temporal decay: meia-vida 30 dias (decisões são atemporais)
             └─ MMR (λ=0.7): diversidade, sem 5 resultados do mesmo parágrafo
```

### Decisões de design

**Exchange-based chunking:** a unidade de indexação não é a mensagem individual, é o *exchange* completo (pergunta + resposta). A resposta isolada da pergunta que a motivou perde grande parte do contexto recuperável.

**Indexação seletiva de blocos internos:** `thinking` e `tool_result` são ruidosos. Só são indexados quando contêm marcadores de valor como `"decidimos"`, `"root cause"`, `"trade-off"`, `"ADR"`. Com peso reduzido (0.6–0.7) para não competir com conteúdo explícito.

**Fuzzy com heurística de doc count:** tokens com até 10 documentos no vocabulário FTS5 são tratados como possíveis typos e passam pelo fuzzy. Palavras comuns (`"como"`, 182 docs) usam busca literal. Evita expansões ruidosas sem suprimir correções legítimas.

**Append-only indexing:** sessões que cresceram têm apenas os novos chunks adicionados. Reduz o custo de reindexação em 10 a 50x para sessões longas.

**Graceful degradation:** sem Ollama, o sistema opera em modo FTS5-only. A indexação continua, a busca por keywords funciona. O modo híbrido é restaurado automaticamente quando o Ollama voltar.

**Piso de confiança vetorial:** resultados recuperados exclusivamente pelo motor vetorial (sem match FTS5) são descartados se o score estiver abaixo de 0.42. Quando um termo não existe no corpus, a busca vetorial devolve os vizinhos mais próximos mesmo que a distância de cosseno seja alta (similaridade ~0.29). Nesse caso, o sistema prefere retornar zero resultados a retornar ruído. Resultados com contribuição FTS5 passam sempre, porque o match literal é prova de que o termo existe no corpus.

**Ponderação adaptativa por tipo de query:** antes de buscar, o sistema classifica a query. Se há stop words semânticas, usa modo híbrido 70/30. Se a query é curta e técnica (até 2 tokens significativos), usa modo FTS5-dominante 25/75. Se todos os tokens são termos técnicos (ALL-CAPS, acrônimos de 2 a 3 letras, nomes como `BERTimbau`, ou raros no corpus), também usa FTS5-dominante. Isso resolve um desequilíbrio estrutural: FTS5 nunca pontua acima de 0.30 com os pesos padrão, enquanto ruído vetorial frequentemente ultrapassa esse valor.

---

## Stack

| Componente | Papel |
|---|---|
| **SQLite WAL** | Banco único, crash-safe, sem servidor |
| **sqlite-vec** | Busca vetorial por similaridade de cosseno |
| **FTS5** | Índice de texto completo com ranking BM25 |
| **qwen3-embedding:4b** | Embeddings multilíngues instruction-aware (MTEB score 69.45) |
| **Ollama** | Runtime local para o modelo de embedding |
| **rapidfuzz** | Fuzzy matching em C++, cerca de 0.2ms por token |
| **Click** | Interface de linha de comando |

**Por que qwen3-embedding:4b e não nomic-embed-text?**

O corpus mistura português com terminologia técnica em inglês. O `nomic-embed-text` funciona bem para inglês monolíngue. Para recuperação cross-lingual num corpus técnico misto, o Qwen3 oferece ganho mensurável: MTEB multilingual 69.45 vs ~60. A dimensão foi fixada em 1024 (não 2560, o máximo do modelo) porque em sistema híbrido o vetor não carrega sozinho toda a carga semântica. 1024 é o ponto de equilíbrio entre qualidade e custo.

---

## Configuração

Todos os parâmetros têm defaults razoáveis. Sobrescreva via variáveis de ambiente quando necessário:

```bash
TOTAL_RECALL_DATA=~/.total-recall           # Diretório de dados
TOTAL_RECALL_SESSIONS=~/.claude/projects    # Raiz dos JSONLs
TOTAL_RECALL_SIBLING_DB=~/.total-recall-codex/total-recall-codex.db  # Banco do total-recall-codex (busca cruzada, read-only)
TOTAL_RECALL_EMBED_PROVIDER=ollama          # ollama | openai
TOTAL_RECALL_OLLAMA_MODEL=qwen3-embedding:4b
TOTAL_RECALL_EMBEDDING_DIMENSIONS=1024      # 512 a 2560; 1024 é o ponto ideal
TOTAL_RECALL_EMBED_USE_QUERY_INSTRUCTION=true
TOTAL_RECALL_FUZZY_THRESHOLD=0.70           # Similaridade mínima para fuzzy
TOTAL_RECALL_FUZZY_MAX_EXPANSIONS=5         # Máximo de variantes por token
OPENAI_API_KEY=...                          # Apenas se provider=openai
```

---

## Performance

Projetado para uso individual, centenas a alguns milhares de sessões.

| Métrica | Valor |
|---|---|
| Busca P50 | ~260ms |
| Busca P95 | ~270ms |
| Fuzzy matching | ~0.2ms por token |
| Reindexação incremental | menos de 1s para sessões que cresceram |
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
│   ├── test_search.py        # Suite: fuzzy, highlighting, benchmark P95
│   ├── test_crossover.py     # Suite: banco read-only, recall_cross, origem nos formatos
│   ├── test_preview_window.py # Trecho centralizado no match, cobertura multi-termo
│   ├── test_fts5_score.py    # Direção do score FTS5, dedup por chunk_id
│   ├── test_compound_split.py # Split de palavra composta colada
│   └── test_table_format.py  # Barra de cobertura ░▒█, --format table
├── docs/
│   ├── GUIA-USUARIO.md       # Referência completa de sintaxe e exemplos
│   ├── exemplos-clipping/    # Clippings reais do desenvolvimento
│   └── HANDOFF-*.md          # Decisões arquiteturais documentadas
└── APRENDIZADOS.md           # Registro técnico por sessão de desenvolvimento
```

**Runtime** (criado por `total-recall init`):

```
~/.total-recall/
├── total-recall.db     # SQLite único: sessions, chunks, vetores, FTS, cache
├── exports/            # Sessões exportadas em Markdown
└── clips/              # Clippings de busca
```

---

## Referências

O design converge com a arquitetura do [OpenClaw](https://openclawlab.com/en/docs/concepts/memory/), que usa busca híbrida vetor+BM25, MMR, temporal decay e sqlite-vec, e serviu como referência de validação. A implementação é independente: Python, específica para sessões do Claude Code, com extensões originais como exchange-based chunking, indexação seletiva de blocos internos, decay com exceção para decisões, role weights e tolerância léxica multicamada. Nenhum código foi derivado do OpenClaw.

---

*Projeto independente. Não tem vínculo com o Memória Viva.*
