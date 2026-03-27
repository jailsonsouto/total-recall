# Prompt para Claude Code Opus - Branch A

Use este projeto como base:

`/Users/criacao/Library/CloudStorage/OneDrive-Embelleze/MEUS-PROJETOS-IA/AGENTES/CLAUDE/projetos/vozes-da-comunidade`

Sua missao e implementar o **Branch A**, que nao e uma mudanca arquitetural total do produto. E um branch de **saneamento do pipeline atual + blindagem operacional para full run com sabiazinho-4**.

## O que motivou este branch

Ha tres fontes de evidencia que precisam ser reconciliadas:

1. os relatorios e benchmarks ja produzidos no projeto
2. os achados do corpus completo de `4.804` comentarios
3. o post-mortem do run fracassado com Maritaca, que desperdicou chamadas por falha tardia e ausencia de persistencia incremental

## Leia obrigatoriamente estes arquivos antes de codar

- `docs/RELATORIO_BENCHMARK_SESSAO_2026-03-27.md`
- `docs/PESQUISA_ARQUITETURA_GATE_ABSA_2026-03-27.md`
- `docs/DIAGNOSTICO_RUN_CORPUS_2026-03-27.md`
- `docs/HANDOFF_OPUS_LACUNAS_EVIDENCIAS_CORPUS_COMPLETO_2026-03-27.md`
- `docs/AVALIACAO_GANHO_NEGOCIO_EMBELLEZE_GATE_ABSA_2026-03-27.md`
- `docs/SPEC_BRANCH_A_SANEAMENTO_PIPELINE_E_FULL_RUN_SABIAZINHO_2026-03-27.md`
- `docs/CHECKLIST_BRANCH_A_FULL_RUN_SABIAZINHO_2026-03-27.md`

## Objetivo do branch

Entregar um pipeline atual saneado, auditavel e seguro para executar o corpus total com `sabiazinho-4`, sem repetir o fracasso operacional anterior.

## O que voce deve implementar

### 1. Router alinhado ao schema atual

- alinhar `interaction_type` ao schema real do corpus V1
- parar de aceitar comentarios por fallback legado inadequado
- impedir que `reply_or_conversation` contamine o slice ASTE principal

### 2. Gate auditavel

Salvar por comentario:

- `comment_id`
- `interaction_type`
- `router_decision`
- `gate_classification`
- `gate_reason`
- texto ou snippet

### 3. Runner resiliente para Maritaca / Sabiazinho

O runner precisa:

- suportar `resume`
- salvar incrementalmente
- evitar reprocessar comentarios ja concluidos
- sobreviver a falha tardia sem perda total
- registrar tokens, custo estimado e erros

### 4. Full run no corpus total

Depois do saneamento:

- rodar um smoke test pequeno
- rodar uma amostra intermediaria
- rodar o corpus total

## O que voce NAO deve fazer

- nao tratar este branch como reconfiguracao completa de arquitetura
- nao declarar `sabiazinho-4` como solucao final do produto
- nao usar apenas contagem de triplas como criterio de sucesso
- nao rerodar cegamente o corpus inteiro sem checkpoint nem deduplicacao

## Criterio de sucesso

O branch so sera considerado bem-sucedido se:

1. o pipeline estiver semanticamente mais limpo
2. o slice ASTE principal nao estiver contaminado por replies
3. o gate ficar auditavel por comentario
4. o run do corpus total com `sabiazinho-4` puder ser feito sem desperdiço evitavel de API
5. houver artefatos finais reproduziveis

## Entregaveis obrigatorios

- codigo do branch
- runner resiliente
- artefato final por comentario do corpus total
- relatorio final do run
- explicacao curta do que mudou, por que mudou e o que ainda ficou em aberto

## Regra metodologica

Separe claramente:

- o que foi provado
- o que foi inferido
- o que ainda precisa de validacao posterior

## Ponto central

Este branch existe para sanar duas falhas ao mesmo tempo:

1. **falha semantica do pipeline**
2. **falha operacional do full run com Maritaca**

Se voce corrigir apenas uma delas, o branch ficara incompleto.

