# Total Recall

Memória pesquisável para sessões do Claude Code CLI.

Indexa todos os transcripts JSONL do Claude Code em SQLite (sqlite-vec + FTS5) com embeddings locais, permitindo recuperar qualquer conversa passada via busca semântica + keyword.

## O Problema

Sessões do Claude Code são voláteis — quando acabam, o contexto se perde. Os JSONL brutos existem em `~/.claude/projects/` mas são opacos e não pesquisáveis. O Total Recall resolve isso.

## Como Funciona

```
~/.claude/projects/**/*.jsonl   (sessões brutas)
         ↓ total-recall index
~/.total-recall/total-recall.db (SQLite: chunks + vetores + FTS5)
         ↓ total-recall search "query"
Resultados com sessão, data, e contexto relevante
```

## Instalação

```bash
# Requer Python 3.9+ e Ollama (opcional, para busca semântica)
cd projetos/total-recall
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Inicializa banco + instala skill /recall
total-recall init

# Indexa todas as sessões
total-recall index
```

### Embedding (opcional, mas recomendado)

```bash
# Instala Ollama: https://ollama.com
ollama pull nomic-embed-text
# Reindexar com embeddings:
total-recall index --full
```

Sem Ollama, o sistema funciona em modo FTS5-only (busca por palavras-chave).

## Uso

```bash
# Busca em todas as sessões
total-recall search "como decidimos sobre pgvector"

# Formato para injeção no Claude
total-recall search "arquitetura memoria viva" --format context

# Lista sessões indexadas
total-recall sessions

# Exporta sessão para Markdown
total-recall export 31c6d284

# Status do sistema
total-recall status

# Reindexar tudo (inclui subagentes)
total-recall index --full --subagents
```

### Skill /recall no Claude Code

Após `total-recall init`, a skill `/recall` fica disponível:

```
/recall o que decidimos sobre a arquitetura de memória?
```

O Claude recebe os trechos relevantes e responde com contexto das sessões passadas.

## Stack

- **SQLite** WAL mode — banco único, crash-safe
- **sqlite-vec** — busca vetorial por similaridade semântica
- **FTS5** — busca por palavras-chave (BM25)
- **nomic-embed-text** via Ollama — embeddings locais, gratuitos (768 dims)
- **Click** — CLI

## Arquitetura

- **Exchange-based chunking**: pergunta + resposta = 1 unidade semântica
- **Busca híbrida**: 70% vetor + 30% FTS5
- **Temporal decay**: sessões recentes pesam mais (meia-vida 30 dias)
- **Exceção para decisões**: chunks com "decidimos", "ADR", "vs" não decaem
- **MMR re-ranking**: diversidade nos resultados (evita redundância)
- **Delta indexing**: só processa arquivos novos/alterados (SHA-256)
- **Graceful degradation**: funciona sem Ollama (modo FTS5-only)
