# Memória Viva — Contexto do Projeto

## O que é
Agente 8 (Memory Manager) do sistema multi-agente de briefing de produto Novex/Embelleze.
Transforma o sistema de "ferramenta que responde" em "sistema que aprende".

## Contexto de origem
Planejado integralmente na sessão Claude + Jay de Março/2026.
Transcrição completa: `/TRANSCRICAO-COMPLETA-CHAT-novex-agentes-memoria.md`

## Inspirações técnicas
- **OpenClaw** — padrões de workspace files, pre-compaction flush, session pruning
- **LangGraph SqliteSaver** — checkpoints de estado por nó
- **ChromaDB** — busca semântica por embeddings

## Arquitetura (resumo)
3 camadas de memória:
- **Hot Store** — SQLite + LangGraph State (o que está acontecendo agora)
- **Warm Store** — ChromaDB (o que é relevante buscar)
- **Cold Store** — Filesystem Markdown + Git (o que aconteceu — legível por humanos)

4 momentos de operação:
1. Pré-execução: Memory Read (injeta contexto nos agentes)
2. Pós-execução: Post-briefing Flush
3. Pós-decisão do Comitê: Committee Memory Flush (nunca pode falhar)
4. Manutenção periódica: cron semanal (aging, compaction, pruning, backup)

## Stack técnica
- Python + LangGraph + CrewAI
- SQLite unificado: WAL mode + sqlite-vec (vetorial) + FTS5 (keyword)
- nomic-embed-text via Ollama (local, gratuito, 768 dims)
- Claude Haiku para sínteses / Claude Sonnet para Committee Flush
- Zero servidores, zero SaaS, zero custo operacional

## Estágios de maturidade
| Estágio | Descrição | Prazo |
|---|---|---|
| 1 — Amnésica | Sem implementação (hoje) | — |
| 2 — Episódica | MVP: Hot Store + flush básico | 4 semanas |
| 3 — Semântica | Warm Store + calibração Bayesiana | 3 meses |
| 4 — Estratégica | TD Learning + pattern detection | 6+ meses |

## Documentos deste projeto
- `docs/PRD.md` — Product Requirements Document
- `docs/ARQUITETURA.md` — Arquitetura técnica detalhada
- `docs/ADRs.md` — Architecture Decision Records
- `docs/GLOSSARIO.md` — Termos do domínio
- `ROADMAP.md` — Fases de implementação com milestones
