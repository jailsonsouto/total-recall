# NEXT_STEPS — Vozes da Comunidade

**Atualizado em:** 2026-03-27

## Agora

- Identificar o ambiente Python canônico do projeto antes de diagnosticar novos bugs de código.
- Garantir nesse ambiente as dependências mínimas declaradas em [`pyproject.toml`](../pyproject.toml), em especial `python-dotenv`.
- Rodar `python3 scripts/run_corpus.py --dry-run` no ambiente escolhido e registrar apenas o resultado útil: passou ou falhou, e qual foi o erro curto.

## Se o dry-run passar

- Escolher uma única trilha para o próximo ciclo.
- `Trilha A`: retomar o reprocessamento do corpus com `scripts/run_corpus.py`, preservando `--resume` e os partials.
- `Trilha B`: decidir entre [`docs/SPEC_CICLO_3A_BERTIMBAU_LLM_PROFESSORA.md`](docs/SPEC_CICLO_3A_BERTIMBAU_LLM_PROFESSORA.md) e [`docs/SPEC_CICLO_3B_LLM_LOCAL_UNSLOTH_HF.md`](docs/SPEC_CICLO_3B_LLM_LOCAL_UNSLOTH_HF.md) com protocolo mínimo de benchmark.
- Antes de qualquer run pago maior, validar também o caminho de salvamento final com uma amostra pequena.

## Se o dry-run falhar

- Não iniciar run pago.
- Atualizar [`docs/HANDOFF_TO_CODEX.md`](docs/HANDOFF_TO_CODEX.md) com o erro curto e o contexto do ambiente.
- Corrigir primeiro o ambiente ou o ponto único de falha, sem abrir várias frentes paralelas.

## Depois

- Marcar explicitamente quais documentos de crash são histórico e quais continuam operacionais.
- Opcionalmente criar um setup mínimo reproduzível do ambiente para reduzir falsos negativos em novas sessões.
