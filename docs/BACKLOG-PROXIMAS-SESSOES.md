# Backlog — Próximas Sessões

**Data:** 2026-07-05
**Fonte de verdade detalhada:** `docs/PLANO-ADVISOR-FASTCONTEXT-2026-07-05.md` §4 (problemas
descobertos, priorizados). Este documento é a versão ordenada e acionável para retomada rápida.

---

## Agora (próxima sessão)

1. **Filtro de auto-contaminação do índice em `session_parser.py`** — descartar/despriorizar
   chunks que são eco do próprio `/recall`. Padrões a excluir: `total-recall search "`,
   `<task-notification>`, "busca disparada em segundo plano" (e variações de invocação de
   skill/comando ecoado). Depois de implementado: reindexar e validar rodando as mesmas 5
   queries do estudo empírico de 2026-07-05 (ver `docs/PLANO-ADVISOR-FASTCONTEXT-2026-07-05.md`
   §3) para confirmar que o ruído de eco sumiu sem perder evidência real.
2. **Commitar/mergear a branch `vingador-do-sonnet`** se aprovada pelo usuário.

## Observação contínua (~2 semanas)

- Avaliar Haiku no sub-agente do `/recall` (mudança aplicada em 2026-07-05, decisão #2 do
  plano). Critério de rollback: fallback Sonnet disparando em mais de 1/3 das buscas, ou
  sínteses percebidas como piores pelo usuário. Anotar toda ocorrência relevante no
  `APRENDIZADOS.md`.

## Explorações (quando houver folga)

- Experimento **FastContext-4B local via Ollama** como explorador de código (GGUF Q4_K_M,
  ~2.5GB; harness com Read/Glob/Grep + parse de `<final_answer>`; repo
  `github.com/microsoft/fastcontext`).
- Levar `--format pointers` para a camada 2 do `/maestro`, depois que o formato se provar em
  uso real dentro do `/recall`.
- Advisor tool da Anthropic: só considerar se/quando o brainiac migrar de `claude -p` para o
  SDK (revogando a decisão D-LLM-2 vigente).

## Visão (o futuro brilhante)

Um ecossistema de agentes em camadas: o trabalho braçal — busca em sessões passadas,
exploração de código, coleta de fatos — roda em modelos locais/baratos de custo zero
(Ollama: `qwen3-embedding` já em produção, `FastContext-4B` candidato), enquanto os modelos
fortes ficam livres para julgamento e síntese. O total-recall funciona como memória
institucional limpa (índice sem eco de si mesmo), alimentando `/recall`, `/maestro` e
`fonte-da-verdade` com evidência citável por sessão. **Modelo fraco para o braço, modelo
forte para o juízo — e toda decisão de comportamento validada com dados reais de uso.**
