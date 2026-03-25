# Total Recall

Memória pesquisável para sessões do Claude Code CLI.

## O que é
Ferramenta standalone que indexa TODOS os transcripts JSONL do Claude Code em SQLite (sqlite-vec + FTS5) com embeddings locais (qwen3-embedding:4b via Ollama, 1024 dims, instruction-aware), permitindo busca semântica + keyword de qualquer conversa passada.

## Stack
- Python >= 3.11
- SQLite WAL + sqlite-vec + FTS5
- qwen3-embedding:4b via Ollama (1024 dims, multilíngue, instruction-aware)
- Click para CLI

## Estrutura
- `src/total_recall/` — módulos Python
- `skill/recall.md` — skill /recall para Claude Code
- `docs/` — documentação técnica e planos de implementação

## Convenções
- APRENDIZADOS.md é artefato obrigatório: ler no início, atualizar ao encerrar
- Runtime data vai para ~/.total-recall/ (DB, exports)
- Sessões JSONL ficam em ~/.claude/projects/ (readonly, nunca modifica)
- **Planos e documentação técnica vão em `docs/`** — persistem no git, não apenas em ~/.claude/plans/

## IMPORTANTE
Este projeto é INDEPENDENTE do Memória Viva. Não tem conexão funcional.
Pode ter padrões de código copiados de lá, mas nunca referências diretas.
