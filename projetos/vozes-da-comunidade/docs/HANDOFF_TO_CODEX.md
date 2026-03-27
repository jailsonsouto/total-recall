# HANDOFF_TO_CODEX — Vozes da Comunidade

Use este bloco quando a retomada depender de outro agente, outra sessão ou de ajuda mais profunda com ambiente e execução.

```text
Retomar a partir deste estado:

Projeto:
vozes-da-comunidade

Objetivo atual:
restabelecer um caminho seguro para retomar o pipeline ASTE/ABSA sem consumir API paga prematuramente e sem confiar cegamente em docs históricas

Estado verificado:
- o repositório já usa docs/ como base documental e agora tem docs/STATE.md, docs/DECISIONS.md e docs/NEXT_STEPS.md como camada curta de retomada
- src/vozes_da_comunidade/batch/gate.py existe e usa GateDecision.classification
- scripts/run_corpus.py existe e já inclui save incremental, --resume, --dry-run e uso de dec.classification.value
- em 2026-03-27, /usr/bin/python3 scripts/run_corpus.py --dry-run falhou com ModuleNotFoundError: No module named 'dotenv'
- pyproject.toml declara python-dotenv>=1.0.0, então o erro parece ser de ambiente e nao de requisito ausente do projeto

Arquivos-chave:
- docs/STATE.md
- docs/NEXT_STEPS.md
- scripts/run_corpus.py
- src/vozes_da_comunidade/batch/gate.py
- pyproject.toml

O que ja foi tentado:
- leitura dos docs principais de PRD, ADRs, roadmap e post-mortem
- verificacao do fonte atual para confirmar que parte do pos-crash ja foi incorporada
- tentativa de dry-run local com /usr/bin/python3

Bloqueio atual:
nao esta claro qual ambiente Python deve ser tratado como canonico; o interpretador de sistema falha antes do dry-run completar

Opcoes em aberto:
1. localizar e ativar o ambiente Python ja usado pelo projeto
2. criar/normalizar um ambiente novo com as dependencias declaradas e validar o dry-run nele
3. tornar o carregamento de dotenv opcional para reduzir atrito local, se isso fizer sentido para a equipe

Recomendacao atual:
priorizar a opcao 1; se nao houver ambiente existente confiavel, seguir para a opcao 2 e so depois decidir entre a trilha de corpus e a trilha 3A/3B

Pedido objetivo:
identificar ou normalizar o ambiente Python canonico, fazer scripts/run_corpus.py --dry-run passar sem consumir API e entao recomendar se o proximo ciclo deve seguir a trilha de corpus seguro ou a adjudicacao 3A vs 3B
```
