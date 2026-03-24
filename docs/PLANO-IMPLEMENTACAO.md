# Total Recall — Plano de Implementação

## Contexto

As sessões do Claude Code CLI são armazenadas como JSONL em `~/.claude/projects/`, mas não são pesquisáveis. Quando uma sessão morre (bateria, compressão de contexto, fechamento), o raciocínio é perdido. O auto-memory (`memory/`) salva apenas o que Claude julga relevante — migalhas. O JSONL bruto tem tudo, mas é opaco.

**Total Recall** resolve isso: indexa todos os transcripts em SQLite (sqlite-vec + FTS5) com embeddings locais (nomic-embed-text via Ollama), e expõe uma skill `/recall` para busca semântica de dentro de qualquer sessão do Claude Code.

**Projeto independente** — sem vínculo com Memória Viva. Pode copiar padrões/código de lá, nunca editar.

---

## Estrutura do Projeto

```
projetos/total-recall/
├── CLAUDE.md
├── APRENDIZADOS.md
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── src/total_recall/
│   ├── __init__.py
│   ├── config.py             # Paths, pesos, dimensões — tudo centralizado
│   ├── database.py           # SQLite WAL + sqlite-vec + schema DDL
│   ├── embeddings.py         # NomicEmbedProvider (copiado do memoria-viva)
│   ├── models.py             # SessionInfo, Chunk, SearchResult, RecallContext
│   ├── vector_store.py       # Hybrid search: 70% vetor + 30% FTS5
│   ├── session_parser.py     # Lê JSONL, extrai exchanges, chunka
│   ├── session_discovery.py  # Escaneia ~/.claude/projects/, detecta novos/alterados
│   ├── indexer.py            # Orquestra: discover → parse → embed → store
│   ├── recall_engine.py      # Busca + temporal decay + MMR re-ranking
│   ├── cold_export.py        # Exporta sessão para Markdown
│   └── cli.py                # Click CLI
├── skill/
│   └── recall.md             # Skill /recall para Claude Code
└── tests/
    ├── __init__.py
    ├── test_session_parser.py
    └── test_recall_engine.py
```

Runtime (criado por `total-recall init`):
```
~/.total-recall/
├── total-recall.db     # SQLite único (WAL mode)
└── exports/            # Markdown das sessões exportadas
```

---

## Schema do Banco

```sql
CREATE TABLE sessions (
    session_id    TEXT PRIMARY KEY,
    project_path  TEXT NOT NULL,
    project_label TEXT,
    title         TEXT,
    started_at    TIMESTAMP,
    ended_at      TIMESTAMP,
    user_messages INTEGER DEFAULT 0,
    asst_messages INTEGER DEFAULT 0,
    file_path     TEXT NOT NULL UNIQUE,
    file_hash     TEXT NOT NULL,
    file_size     INTEGER DEFAULT 0,
    is_subagent   BOOLEAN DEFAULT FALSE,
    parent_session_id TEXT,
    indexed_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE chunks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL REFERENCES sessions(session_id),
    role          TEXT NOT NULL,       -- 'user', 'assistant', 'exchange'
    content       TEXT NOT NULL,
    timestamp     TIMESTAMP,
    chunk_index   INTEGER NOT NULL,
    line_start    INTEGER,
    line_end      INTEGER,
    has_embedding BOOLEAN DEFAULT TRUE,
    embed_model   TEXT,
    metadata      TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE chunks_vec USING vec0(embedding float[768]);
CREATE VIRTUAL TABLE chunks_fts USING fts5(content, session_id, role);

CREATE TABLE embedding_cache (
    text_hash  TEXT PRIMARY KEY,
    embedding  BLOB NOT NULL,
    model      TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE indexing_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at       TIMESTAMP,
    files_scanned  INTEGER DEFAULT 0,
    files_indexed  INTEGER DEFAULT 0,
    chunks_created INTEGER DEFAULT 0,
    errors         TEXT
);
```

---

## Decisões Arquiteturais Chave

### 1. Exchange-based chunking (não por mensagem)
Cada par pergunta-resposta (user + assistant) vira UM chunk semântico. "Q: como decidimos sobre pgvector? A: Decidimos pelo sqlite-vec..." é muito mais buscável do que pergunta e resposta separadas. Respostas longas são divididas com overlap de 200 chars.

### 2. Graceful degradation (modo FTS-only)
Se Ollama não está rodando, o sistema funciona com busca por palavras-chave via FTS5. Chunks são armazenados com `has_embedding=FALSE` e indexados no FTS5 normalmente. Embedding pode ser gerado depois com `total-recall index`.

### 3. Temporal decay com exceção para decisões
`score_ajustado = score * 2^(-dias / 30)`. Meia-vida de 30 dias. MAS chunks com palavras como "decidimos", "ADR", "trade-off", "vs", "escolhemos" NÃO decaem — decisões arquiteturais são atemporais.

### 4. Delta indexing via SHA-256
Cada JSONL indexado tem seu hash armazenado. No reindex incremental, só processa arquivos novos ou alterados. Arquivos "alterados" (sessão que cresceu) são deletados e reindexados por completo — mais simples que diff parcial.

### 5. Subagents opcionais
Os 33 subagent JSONLs (aside_question, compact) são curtos e ruidosos. NÃO indexados por padrão. Flag `--subagents` habilita.

### 6. MMR diversity re-ranking
Evita retornar 5 chunks da mesma sessão sobre o mesmo tema. Lambda=0.7 (70% relevância, 30% diversidade).

---

## Skill `/recall`

Arquivo `skill/recall.md` (instalado em `~/.claude/commands/recall.md`):

```markdown
---
allowed-tools: Bash(total-recall search:*), Bash(total-recall sessions:*)
description: Search past Claude Code sessions for topics, decisions, or conversations.
  Use when the user wants to recall something from a previous session.
argument-hint: <query about past sessions>
---

Run: total-recall search "$ARGUMENTS" --format context --limit 8

Analyze the results and present:
- Direct answer citing session ID and date
- Relevant excerpts as evidence
- Related topics found
```

---

## CLI

```
total-recall init                          # Cria DB + dirs + instala skill
total-recall index [--full] [--subagents]  # Indexa sessões (incremental default)
total-recall search "query" [-n 5] [-s ID] # Busca híbrida
total-recall sessions [--project X]        # Lista sessões indexadas
total-recall export <session-id>           # Exporta para Markdown
total-recall status                        # Saúde do sistema
```

---

## Fontes de Código (COPIAR, nunca editar)

| Origem | O que copiar | Adaptação |
|--------|-------------|-----------|
| `memoria-viva/database.py` | Database class, WAL, sqlite-vec loading, transaction() | Schema total-recall, paths |
| `memoria-viva/vector_store.py` | SQLiteVectorStore, hybrid_search() | Adicionar session_id no FTS, join com sessions |
| `memoria-viva/embeddings.py` | NomicEmbedProvider, text_hash(), factory | Import paths |
| `memoria-viva/config.py` | Padrão centralizado com env fallbacks | Constantes total-recall |
| `memoria-viva/cli.py` | Estrutura Click | Comandos total-recall |
| `jsonl_to_markdown.py` | extract_text_content(), format_timestamp() | Adaptar para session_parser |

---

## Fases de Implementação

### Fase 1 — Fundação
1. Scaffolding: `pyproject.toml`, `__init__.py`, `.gitignore`, `.env.example`, `CLAUDE.md`
2. `config.py` — todas as constantes
3. `models.py` — dataclasses
4. `database.py` — schema + conexão (copiar padrão do memoria-viva)
5. `embeddings.py` — NomicEmbedProvider (copiar do memoria-viva)
6. `cli.py` parcial — apenas `init` e `status`
7. **Validação**: `total-recall init` funciona, DB criado, embedding testado

### Fase 2 — Core Engine
8. `session_parser.py` — parsing JSONL + chunking (adaptar jsonl_to_markdown.py)
9. `session_discovery.py` — scan + delta detection
10. `vector_store.py` — hybrid search (copiar do memoria-viva)
11. `indexer.py` — orquestração
12. `cli.py` — adicionar `index` e `sessions`
13. **Validação**: `total-recall index` indexa as 6 sessões, `total-recall sessions` lista

### Fase 3 — Busca Inteligente
14. `recall_engine.py` — temporal decay + MMR
15. `cli.py` — adicionar `search`
16. **Validação**: `total-recall search "pgvector vs sqlite"` retorna resultados relevantes

### Fase 4 — Integração
17. `cold_export.py` — export para Markdown
18. `skill/recall.md` — skill Claude Code
19. `cli.py` — adicionar `export`, instalar skill no `init`
20. Testes
21. `README.md`, `APRENDIZADOS.md`
22. **Validação end-to-end**: abrir nova sessão Claude Code, `/recall como decidimos sobre pgvector` funciona

---

## Verificação

1. `total-recall init` → DB criado em `~/.total-recall/`
2. `total-recall index` → 6 sessões principais indexadas, ~200+ chunks
3. `total-recall search "pgvector vs chromadb"` → encontra a discussão do dia 22/03
4. `total-recall search "memoria viva arquitetura"` → cross-session results
5. `total-recall sessions` → lista bate com os JSONLs existentes
6. `total-recall export <id>` → Markdown legível
7. `/recall` em nova sessão Claude Code → Claude recebe contexto e raciocina
