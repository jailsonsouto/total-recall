# Spec - Branch A: saneamento do pipeline ASTE/ABSA + full run seguro no Sabiazinho

**Projeto:** Vozes da Comunidade  
**Data:** `2026-03-27`  
**Branch sugerido:** `codex/branch-a-saneamento-pipeline-sabiazinho`

## 1. Status

Spec ativa para o proximo branch de correcao do pipeline atual.

Esta spec consolida:

- os achados do benchmark e dos relatorios do Claude/Opus
- os achados do corpus completo de `4.804` comentarios
- o post-mortem do run desperdicado na API Maritaca

Ela **nao** e a spec da reconfiguracao arquitetural de 3 trilhas.
Ela e a spec do **saneamento do pipeline atual** para que o proximo nivel seja construido em base limpa.

## 2. Problema

O pipeline atual ainda mistura problemas semanticos e problemas operacionais:

1. o `Router` esta parcialmente desalinhado com o schema real do corpus V1
2. o slice `ASTE_READY` esta contaminado por `reply_or_conversation` e por contexto `[PARENT]/[REPLY]`
3. o `Gate` ainda produz buckets heterogeneos, especialmente `off_topic`
4. o projeto ainda nao possui um run robusto e reproduzivel do corpus total com `sabiazinho-4`
5. ja houve desperdicio de chamadas na API Maritaca por falha tardia e ausencia de save incremental

## 3. Objetivo do branch

Entregar um pipeline atual saneado, auditavel e operacionalmente seguro, capaz de:

- produzir um slice `ASTE_READY` mais limpo
- preservar valor analitico de `absa_implicit` e `claim_question`
- executar o corpus total no `sabiazinho-4` sem perda de resultados por falha tardia
- gerar artefatos auditaveis por comentario

## 4. O que esta provado ate aqui

- `sabiazinho-4` parece o melhor extrator ASTE operacional atual no slice benchmarkado
- a decisao principal do projeto ainda nao e so "qual modelo usar"
- o corpus completo mostra:
  - `reply_or_conversation` vazando para ASTE
  - `absa_implicit` com muito mais sinal de produto do que o pipeline assume
  - `claim_question` com valor claro para descoberta
  - `off_topic` semanticamente heterogeneo
- o run anterior do corpus com Maritaca falhou de forma evitavel por bug de atributo, ausencia de persistencia incremental e execucao fragil

## 5. Hipotese central

Se corrigirmos a fronteira semantica do pipeline atual e adicionarmos resiliencia operacional ao run do corpus, entao:

- a comparacao entre extratores ASTE ficara mais honesta
- o `sabiazinho-4` podera ser testado no corpus total sem desperdiço de API
- os dados produzidos ficarao bons o bastante para sustentar o proximo ciclo arquitetural

## 6. Escopo do Branch A

### Em escopo

1. alinhar `Router` ao schema normalizado atual do corpus
2. impedir que `reply_or_conversation` contamine o slice ASTE principal
3. tornar o `Gate` auditavel por comentario
4. revisar a semantica de `off_topic`
5. manter `absa_implicit` e `claim_question` como buckets explicitamente valiosos
6. implementar um runner robusto para `sabiazinho-4` no corpus total
7. adicionar persistencia incremental, resume e protecoes contra reprocessamento inutil
8. produzir artefatos finais comparaveis e reproduziveis

### Fora de escopo

1. reconfiguracao completa do produto para arquitetura de 3 trilhas
2. fine-tuning de BERTimbau
3. substituicao definitiva do backend por outro provedor
4. gold set completo adjudicado
5. redesign total de indicadores de negocio

## 7. Requisitos funcionais

### RF1. Router alinhado ao schema V1

O branch deve explicitar quais `interaction_type` entram e quais saem com base no schema real do corpus atual.

Minimo esperado:

- aceitar explicitamente classes compativeis com analise de produto
- rejeitar explicitamente `reply_or_conversation` para o slice ASTE principal
- remover dependencia de fallbacks legados que aceitam comentario so por comprimento

### RF2. Separacao de comentario simples vs comentario encadeado

Comentarios com `[PARENT]` ou `[REPLY]` devem:

- ser excluidos do slice ASTE principal
- ou ir para uma trilha separada claramente nomeada

O importante e que o benchmark ASTE nao misture comentario isolado com comentario enriquecido por thread.

### RF3. Gate auditavel

O gate deve produzir, por comentario:

- `comment_id`
- `interaction_type`
- `router_decision`
- `gate_classification`
- `gate_reason`
- indicadores auxiliares usados na decisao
- texto ou snippet auditavel

Nao basta um sumario agregado.

### RF4. Buckets semanticos honestos

O branch deve revisar a classificacao atual para evitar que `off_topic` signifique apenas "nao reconhecido pelo gate".

Nao e obrigatorio renomear a classe agora, mas e obrigatorio:

- documentar seu significado real
- quantificar sua heterogeneidade
- reduzir falsos `off_topic` obvios

### RF5. Full run resiliente no `sabiazinho-4`

O runner do corpus total deve incluir no minimo:

- save incremental por lote
- checkpoint de progresso
- possibilidade de resume sem reprocessar o que ja foi salvo
- gravacao de resultados por comentario antes de qualquer sumario final
- captura clara de erros por comentario e erros fatais

### RF6. Guardrails de custo e idempotencia

O run com Maritaca deve ter:

- `dry-run` pequeno antes do full run
- estimativa de custo antes de iniciar
- opcao de limitar numero maximo de comentarios ou batch
- opcao de parar e retomar
- protecao contra reenvio cego de comentarios ja processados

### RF7. Artefatos finais

Ao final, o branch deve produzir:

1. um JSON auditavel por comentario do run no corpus total
2. um sumario agregado
3. um relatorio curto com:
   - contagens
   - custo
   - tempo
   - falhas
   - observacoes sobre qualidade do slice ASTE limpo

## 8. Requisitos nao funcionais

### RNF1. Reprodutibilidade

Todo numero relevante deve poder ser rastreado a:

- commit
- script/entrypoint
- dataset
- artefato salvo

### RNF2. Robustez

Nenhuma falha de sumario final pode apagar o trabalho ja concluido.

### RNF3. Observabilidade

O run deve permitir saber:

- quantos comentarios foram processados
- quantos faltam
- quantos falharam
- quanto custou
- de onde retomar

### RNF4. Seguranca operacional

O branch nao deve depender de execucao frágil em background sem checkpoint.

## 9. Criterios de aceite

O Branch A so sera considerado aceito se:

1. o `Router` estiver alinhado ao schema atual e esse alinhamento estiver documentado
2. o slice ASTE principal excluir `reply_or_conversation` ou os separar claramente
3. existir artefato auditavel por comentario do gate e do full run
4. o runner do `sabiazinho-4` permitir resume sem desperdiçar chamadas ja feitas
5. o corpus total puder ser processado sem risco alto de perda total por falha tardia
6. existir relatorio final com proveniencia suficiente para reproduzir os numeros

## 10. Nao objetivos explicitos

Este branch nao deve:

- promover `sabiazinho-4` como solucao final do produto
- encerrar o debate sobre arquitetura de 3 trilhas
- fingir que benchmark sem gold set e verdade definitiva
- usar "mais triplas" como unico criterio de sucesso

## 11. Ordem recomendada de implementacao

1. corrigir `Router` e documentar o mapping de `interaction_type`
2. isolar `reply_or_conversation` e comentarios com `[PARENT]/[REPLY]`
3. tornar o `Gate` auditavel por comentario
4. implementar runner resiliente da Maritaca
5. rodar smoke test curto
6. rodar amostra intermediaria
7. rodar corpus total
8. gerar relatorio final do branch

## 12. Riscos residuais esperados

Mesmo apos este branch, ainda podem permanecer:

- falsos `absa_implicit` por vocabulario incompleto
- necessidade de trilha propria para `claim_question`
- necessidade de gold set pequeno para validar conclusoes finais de modelo

Esses pontos pertencem ao ciclo seguinte, nao invalidam o Branch A.

## 13. Definition of Done

O branch estara pronto quando houver:

- codigo funcional
- runner resiliente
- run bem-sucedido no corpus total com `sabiazinho-4`
- artefatos completos salvos
- relatorio com numeros reproduziveis
- zero repeticao cega do erro operacional que desperdicou chamadas ontem

