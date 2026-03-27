# STATE — Vozes da Comunidade

**Atualizado em:** 2026-03-27
**Modo de trabalho:** standard
**Objetivo atual:** retomar o projeto com baixo risco, memória mínima e sem consumir API paga antes de validar o caminho operacional ponta a ponta.

## Fatos verificados

- O repositório já usa `docs/` como camada principal de documentação; por isso esta memória operacional fica aqui, e não em `.specs/`.
- O código atual existe em `src/vozes_da_comunidade/`.
- [`src/vozes_da_comunidade/batch/gate.py`](../src/vozes_da_comunidade/batch/gate.py) existe na árvore atual e define `GateDecision.classification`.
- [`scripts/run_corpus.py`](../scripts/run_corpus.py) existe na árvore atual e já inclui `save incremental`, `--resume`, `--dry-run` e uso de `dec.classification.value`.
- Em 2026-03-27, o comando `/usr/bin/python3 scripts/run_corpus.py --dry-run` falhou localmente com `ModuleNotFoundError: No module named 'dotenv'`.
- [`pyproject.toml`](../pyproject.toml) declara `python-dotenv>=1.0.0` como dependência do projeto.

## Inferências úteis

- Parte da documentação de crash ficou historicamente útil, mas não reflete integralmente o estado atual do código.
- O bloqueio imediato mais provável não é mais `gate.py` ausente; é a falta de um ambiente Python canônico pronto para rodar o fluxo.
- O projeto está entre duas frentes diferentes: endurecer o pipeline operacional e decidir a próxima aposta arquitetural (`3A` vs `3B`).

## Ainda precisa de adjudicação

- Qual ambiente Python deve ser tratado como canônico para este repositório.
- Se o próximo ciclo deve priorizar `Trilha A = reprocessar corpus com segurança` ou `Trilha B = decidir 3A/3B`.
- Se os documentos longos de crash devem ser apenas preservados como histórico ou explicitamente marcados como desatualizados.

## Guardrails ativos

- Não registrar segredos, chaves ou endpoints privados nestes arquivos de memória.
- Não rodar chamadas pagas de API antes de um `--dry-run` completo no ambiente Python correto.
- Não misturar as trilhas `3A` e `3B` no mesmo ciclo sem uma decisão explícita.
- Não tratar benchmark pequeno ou acordo entre modelos como verdade semântica.
- Não auto-commitar, não usar comandos destrutivos e não reverter mudanças alheias.

## Riscos abertos

- Documentação histórica conflitante pode induzir uma retomada errada.
- O worktree está sujo; há arquivos do usuário e artefatos paralelos fora do escopo imediato.
- Um falso negativo de ambiente pode parecer bug de código quando é só dependência ausente.
- Um run longo com API ainda carrega risco de custo se o ambiente e o fluxo de salvamento não forem validados antes.

## Arquivos decisivos

- [`README.md`](../README.md)
- [`docs/PRD.md`](docs/PRD.md)
- [`docs/ADRs.md`](docs/ADRs.md)
- [`docs/ESTADO_ATUAL-vozes-da-comunidade-apos-crash-claude-27-marco-2026.md`](docs/ESTADO_ATUAL-vozes-da-comunidade-apos-crash-claude-27-marco-2026.md)
- [`docs/LEMBRETE_ESTADO_ATUAL_ASTE_ABSA_2026-03-27.md`](docs/LEMBRETE_ESTADO_ATUAL_ASTE_ABSA_2026-03-27.md)
- [`scripts/run_corpus.py`](../scripts/run_corpus.py)

## Instrução exata de retomada

Leia este arquivo, depois [`docs/NEXT_STEPS.md`](docs/NEXT_STEPS.md), descubra ou ative o ambiente Python canônico do projeto e rode `python3 scripts/run_corpus.py --dry-run` nesse ambiente antes de qualquer run pago ou nova decisão arquitetural.

**Frase de retomada:** validar o `dry-run` no ambiente Python correto e só então escolher entre reprocessar o corpus com segurança ou avançar para a decisão `3A` vs `3B`.
