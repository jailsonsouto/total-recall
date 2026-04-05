# Total Recall Codex

## O que é
Fork do total-recall adaptado para o Codex Desktop. Indexa transcripts JSONL do Codex em SQLite com embeddings locais, permitindo busca semântica + keyword.

## Stack
- Python >= 3.11
- SQLite WAL + sqlite-vec + FTS5
- qwen3-embedding:4b via Ollama (1024 dims, instruction-aware)
- Click para CLI

## Estrutura
- `src/total_recall_codex/` — módulos Python
- `skill/SKILL.md` — skill para Codex Desktop
- `docs/` — documentação técnica

## Convenções
- APRENDIZADOS.md é artefato obrigatório: ler no início, atualizar ao encerrar
- Runtime data vai para `~/.total-recall-codex/` (DB, exports)
- Sessões JSONL ficam em `~/.codex/sessions/` (readonly, nunca modifica)
- **Isolamento total**: zero sobreposição com `~/.total-recall/` do Claude Code

## IMPORTANTE
Este projeto é um FORK do total-recall original. O original permanece intacto.
Cada instância tem DB, paths e CLI command separados.
