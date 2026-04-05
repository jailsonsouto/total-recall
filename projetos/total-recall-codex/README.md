# Total Recall Codex

Memória pesquisável para sessões do Codex Desktop.

## O Problema

Você usa o Codex Desktop diariamente. Cada sessão gera um arquivo JSONL com todo o histórico da conversa — decisões, diagnósticos, código, planos. Quando você precisa lembrar **"o que decidimos sobre X?"** ou **"como resolvemos Y?"**, precisa vasculhar sessões manualmente.

O Codex não tem memória entre sessões. O contexto morre quando a sessão fecha.

## O que é

Ferramenta standalone que indexa **TODOS** os transcripts JSONL do Codex em SQLite (sqlite-vec + FTS5) com embeddings locais (qwen3-embedding:4b via Ollama, 1024 dims, instruction-aware), permitindo busca semântica + keyword de qualquer conversa passada.

## Capacidades

- **Busca híbrida**: vetor semântico (70%) + keyword FTS5 (30%) com pesos adaptativos
- **Tolerância léxica**: fuzzy matching para typos, expansão de abreviações PT-BR
- **Temporal decay**: sessões recentes pesam mais; decisões arquiteturais são atemporais
- **MMR re-ranking**: diversidade nos resultados (evita chunks redundantes)
- **Graph Lite**: co-ocorrência de entidades para navegação lateral e contradiction detection
- **Clippings**: salve buscas relevantes como Markdown datado
- **Skill Codex**: integração nativa via `/recall` no Codex Desktop

## Instalação

```bash
git clone https://github.com/jailsonsouto/total-recall-codex.git
cd total-recall-codex
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .
ollama pull qwen3-embedding:4b
total-recall-codex init
total-recall-codex index
```

## Uso

### Indexar
```bash
total-recall-codex index          # Incremental (só sessões novas/alteradas)
total-recall-codex index --full   # Reindexação completa
```

### Buscar
```bash
total-recall-codex search "como decidimos usar sqlite-vec"
total-recall-codex search "ChromaDB vs pgvector" --limit 10
total-recall-codex search "deploy" --session c3b0e47e
total-recall-codex search "decisão arquitetura" --clip
```

### Listar sessões
```bash
total-recall-codex sessions
total-recall-codex sessions --project memoria-viva
```

### Exportar
```bash
total-recall-codex export c3b0e47e
```

### Status e diagnóstico
```bash
total-recall-codex status
total-recall-codex doctor
```

## Como Funciona

### Pipeline de Indexação
```
~/.codex/sessions/**/*.jsonl
  → discover (varre por data YYYY/MM/DD/)
  → parse (turn-based: task_started → task_complete)
  → embed (qwen3-embedding:4b, instruction-aware, cache LRU)
  → store (SQLite: chunks + chunks_vec + chunks_fts)
```

### Pipeline de Busca
```
query → classify (semântica vs técnica) → pesos adaptativos
  → FTS5 BM25 (com fuzzy + abreviações)
  → Vector cosine (qwen3-embedding)
  → Hybrid merge (70/30 ou 25/75)
  → Salience rerank (relevância × reforço × recência)
  → MMR diversity
  → Results + provenance
```

## Stack

- Python >= 3.11
- SQLite WAL + sqlite-vec + FTS5
- qwen3-embedding:4b via Ollama (1024 dims, multilíngue, instruction-aware)
- Click para CLI
- rapidfuzz para fuzzy matching

## Configuração

Variáveis de ambiente (opcionais, prefixo `TOTAL_RECALL_CODEX_*`):

| Variável | Default | Descrição |
|----------|---------|-----------|
| `TOTAL_RECALL_CODEX_DATA` | `~/.total-recall-codex/` | Diretório de dados |
| `TOTAL_RECALL_CODEX_SESSIONS` | `~/.codex/sessions/` | Raiz das sessões |
| `TOTAL_RECALL_CODEX_EMBED_PROVIDER` | `ollama` | Provedor de embedding |
| `TOTAL_RECALL_CODEX_OLLAMA_MODEL` | `qwen3-embedding:4b` | Modelo Ollama |
| `TOTAL_RECALL_CODEX_EMBEDDING_DIMENSIONS` | `1024` | Dimensões do embedding |

## Performance

- Indexação incremental: 10-50x mais rápida que reindexação completa
- Busca híbrida: < 100ms para corpus de ~3000 chunks
- Fuzzy matching: +0.2ms sobre FTS5 puro (rapidfuzz em C++)
- Embedding cache: evita chamadas redundantes ao Ollama

## Estrutura

```
src/total_recall_codex/
├── config.py              — Configuração global
├── database.py            — SQLite schema (agnóstico)
├── embeddings.py          — Provider abstraction
├── vector_store.py        — Hybrid search, fuzzy, MMR
├── recall_engine.py       — Temporal decay, salience, MMR
├── models.py              — Dataclasses genéricas
├── indexer.py             — Orquestração de indexação
├── session_parser.py      — Parser JSONL Codex (turn-based)
├── session_discovery.py   — Descoberta de sessões
├── cli.py                 — CLI Click
└── cold_export.py         — Export para Markdown
```

## Isolamento

Zero sobreposição com o total-recall original (Claude Code):

| Recurso | total-recall | total-recall-codex |
|---|---|---|
| Data dir | `~/.total-recall/` | `~/.total-recall-codex/` |
| Database | `total-recall.db` | `total-recall-codex.db` |
| Sessions root | `~/.claude/projects/` | `~/.codex/sessions/` |
| CLI command | `total-recall` | `total-recall-codex` |

Coexistem pacificamente na mesma máquina.
