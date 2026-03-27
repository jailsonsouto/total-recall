# Spec-Driven Development: Ciclo 3A — BERTimbau com LLM professora

## Status

- Estado: proposto
- Data: `2026-03-27`
- Objetivo: decidir e operacionalizar o caminho `LLM professora -> dataset -> BERTimbau`
- Leitor principal: Claude Opus ou outro implementador com autonomia

---

## 1. Proposito deste spec

Este documento define o **Ciclo 3A** do trabalho sobre ASTE/ABSA no projeto Vozes da Comunidade.

O objetivo deste ciclo nao e discutir abstratamente "LLM vs BERT". O objetivo e responder uma pergunta pratica:

> Como transformar o estado atual do projeto em um pipeline de dados e treino que permita ao BERTimbau virar o motor principal de extracao ASTE/ABSA, sem depender de anotacao humana total desde o primeiro dia?

Este spec parte de uma premissa simples:

- LLM forte e melhor **professora inicial**
- BERTimbau fine-tuned e melhor **aluno de producao** para span extraction em PT-BR

O branch deve provar se essa arquitetura e viavel com os artefatos reais do repositorio.

---

## 2. Decisao que este ciclo precisa destravar

Ao fim do branch, o projeto precisa sair com uma decisao explicita sobre estas questoes:

1. o projeto vai adotar oficialmente a arquitetura `LLM professora -> silver/gold -> BERTimbau`?
2. qual sera o papel da LLM professora:
   - apenas bootstrap de dataset
   - bootstrap + active learning
   - bootstrap + fallback em casos dificeis
3. qual versao do BERTimbau sera o alvo inicial:
   - `neuralmind/bert-base-portuguese-cased`
   - `neuralmind/bert-large-portuguese-cased`
4. qual e o menor conjunto de dados versionado que permite um treino inicial serio?

O branch nao precisa entregar o modelo final perfeito. Ele precisa entregar um **caminho de dados e validacao tecnicamente defensavel**.

---

## 3. Linha de base factual atual

As afirmacoes abaixo sao consideradas baseline confiavel porque estao sustentadas por documentos e codigo do repositorio.

### 3.1 O repositorio ja assume BERTimbau como plano principal

Fontes:

- `docs/ADRs.md`
- `docs/PLANO_A_BERTIMBAU.md`
- `docs/ARQUITETURA.md`

Fatos aceitos:

- o projeto ja decidiu em ADR que BERTimbau fine-tuned e o motor principal desejado para ASTE offline
- o motivo central e correto: ASTE exige spans e relacoes estruturadas, o que se alinha melhor a encoder models do que a prompting generativo puro
- o projeto ja tem desenho arquitetural claro para BERTimbau na fase offline e LLM na fase de sintese

### 3.2 O repositorio ainda nao tem dataset ouro suficiente para o Plano A

Fontes:

- `docs/ADRs.md`
- `docs/FINE_TUNING_CICLO.md`
- `docs/PLANO_A_BERTIMBAU.md`

Fatos aceitos:

- sem dataset anotado de qualidade, o BERTimbau nao pode ser promovido
- o projeto descreve `500` exemplos como ponto de partida funcional
- o projeto descreve `2.000` exemplos como faixa de maturidade mais convincente

### 3.3 O pipeline atual melhorou, mas ainda esta em fase de extracao por LLM/SLM

Fontes:

- `docs/SPEC_CICLO_2_VALIDACAO_ASTE_ABSA_HAIKU.md`
- `src/vozes_da_comunidade/batch/gate.py`
- `src/vozes_da_comunidade/extractors/slm.py`
- `src/vozes_da_comunidade/indicators/calculator.py`

Fatos aceitos:

- o pipeline atual ja tem gate, parser endurecido e indicadores mais coerentes
- existe benchmark util entre `qwen2.5:3b`, `qwen2.5:7b` e Haiku
- esse benchmark ajuda a criar dataset e hipoteses, mas nao substitui gold set

### 3.4 O problema real nao e apenas modelo, e tambem dados

Leitura consolidada de ciclos anteriores:

- boa parte do erro veio de comentarios nao `ASTE_READY`
- o projeto ainda nao possui um conjunto ouro pequeno, estratificado e adjudicado
- sem esse conjunto, qualquer comparacao futura entre BERT, Qwen ou API LLM continuara parcialmente ambigua

---

## 4. Hipotese central deste ciclo

### H1: a melhor arquitetura de medio prazo para o projeto e `LLM professora -> BERTimbau de producao`

Racional:

- a LLM professora acelera a producao de rótulos
- o BERTimbau tende a generalizar melhor em tarefa estreita de span extraction em PT-BR, com menor custo operacional
- essa arquitetura preserva um ativo proprietario do projeto em vez de manter dependencia total de API

### H2: o gargalo atual nao e fine-tuning em si; e a ausencia de um pipeline versionado de dados

Sem pipeline de dados, qualquer treino de BERT vira experimento fragil e dificil de repetir.

### H3: silver labels sao aceitaveis para bootstrap, desde que exista um gold set pequeno e separado

Silver labels podem ser gerados por uma LLM professora forte, mas:

- nao podem ser tratados como verdade final
- nao podem contaminar o conjunto de teste
- precisam de filtros de qualidade e de revisao humana minima

---

## 5. Objetivo formal do Ciclo 3A

O branch deste ciclo deve:

1. definir a pipeline oficial de construcao de dataset para o Plano A
2. produzir um gold set pequeno, estratificado e separado do silver
3. produzir um silver set de treino usando LLM professora e filtros objetivos
4. treinar um primeiro baseline do BERTimbau com reproducibilidade
5. comparar o BERTimbau com os baselines atuais no mesmo conjunto ouro
6. decidir se o caminho `LLM professora -> BERTimbau` deve virar prioridade oficial

O branch so sera considerado completo se responder:

> O BERTimbau ja tem base metodologica suficiente para virar o proximo eixo principal do projeto?

---

## 6. Escopo

### Em escopo

- especificacao do dataset
- criacao de gold set
- geracao de silver labels
- fine-tuning inicial de BERTimbau
- avaliacao comparativa
- criterios de promocao

### Fora de escopo

- concluir o TCC
- anotar 2.000 comentarios manualmente neste branch
- substituir definitivamente todos os LLMs do pipeline
- refazer a arquitetura do produto online
- treinar modelos proprietarios do zero

---

## 7. Arquitetura alvo

O branch deve materializar esta arquitetura logica:

```text
Corpus bruto / corpus_v1
  ->
Router + Gate Semantico
  ->
pool elegivel para rotulacao
  ->
LLM professora
  ->
silver labels filtrados
  ->
gold set pequeno adjudicado
  ->
conversao para formato de treino BERTimbau
  ->
fine-tuning inicial
  ->
avaliacao no gold set
  ->
decisao de promocao ou nao
```

---

## 8. Regras metodologicas obrigatorias

### RM-1: separar claramente `gold`, `silver` e `test`

Definicoes obrigatorias:

- `gold`: comentarios revisados e adjudicados
- `silver`: comentarios rotulados por LLM professora, com filtros
- `test`: subconjunto exclusivamente gold, nunca usado em treino

Proibicoes:

- nao usar silver como teste final
- nao misturar gold com treino sem registrar a divisao
- nao relatar performance sem informar em qual conjunto ela foi medida

### RM-2: o gold set deve ser estratificado por dificuldade real

O gold set nao pode ser amostra aleatoria cega.

Ele deve incluir, no minimo:

- `ASTE_READY` claros
- `ABSA_IMPLICIT`
- perguntas/claims que devem abster
- off-topic residual
- ironia/negacao/emojis relevantes

### RM-3: a LLM professora nao e oraculo

A LLM professora pode acelerar rotulacao, mas:

- pode alucinar spans
- pode super-extrair
- pode errar polaridade em ironia e pergunta

Todo silver set precisa de filtros programaticos de plausibilidade.

### RM-4: o branch deve medir tarefa, nao vaidade

Metricas obrigatorias:

- `aspect_span_f1`
- `opinion_span_f1`
- `pair_f1`
- `polarity_f1`
- `ASTE_F1`
- taxa de abstencao correta em comentarios nao `ASTE_READY`

Nao e aceitavel reportar apenas:

- numero de triplas
- perda de treino
- acuracia por token isolada

### RM-5: a comparacao final deve ser feita no mesmo conjunto ouro

O BERTimbau deve ser comparado, quando possivel, com:

- baseline local atual (`qwen2.5:3b` ou default vigente)
- referencia forte de professora usada no silver

Se o benchmark nao for totalmente comparavel, isso deve ser explicitado.

---

## 9. Decisoes de produto que o implementador esta autorizado a tomar

O implementador pode decidir sem nova aprovacao do usuario:

1. usar `bert-base` ou `bert-large` como baseline inicial, desde que justifique em funcao de hardware e latencia
2. limitar o primeiro ciclo a `ASTE_READY` + pequena faixa de `ABSA_IMPLICIT`
3. usar silver labels como pretreino do lote inicial
4. incluir pequena quantidade de gold no treino, desde que o conjunto de teste continue blindado
5. manter LLM professora como fallback de casos dificeis, se isso surgir dos dados

O implementador nao pode assumir sem registrar:

- que silver labels equivalem a gold
- que BERT ja esta pronto para producao so porque treinou sem erro

---

## 10. Especificacao do dataset

### 10.1 Unidades obrigatorias

Cada exemplo precisa preservar, no minimo:

- `comment_id`
- `text_for_model`
- `interaction_type`
- `eligibility`
- `gate_decision`
- `gate_reason`
- `teacher_model`
- `teacher_prompt_version`
- `triplets`
- `label_source` (`gold_human`, `silver_teacher`, `gold_adjudicated`)
- `quality_flags`

### 10.2 Formatos obrigatorios

O branch deve gerar ao menos dois formatos:

1. formato de anotacao/inspecao humana
   - `jsonl` ou `csv` auditavel

2. formato de treino BERT
   - CoNLL/BIO ou estrutura equivalente reproduzivel

### 10.3 Politica de construcao do gold set

Recomendacao minima:

- `150–300` comentarios adjudicados

Composicao desejada:

- `50%` `ASTE_READY`
- `15–20%` `ABSA_IMPLICIT`
- `15–20%` perguntas/claims
- `10–15%` off-topic/social
- diversidade de ironia, negacao e ruido informal

### 10.4 Politica de construcao do silver set

Recomendacao minima:

- `1.000–5.000` comentarios elegiveis, dependendo de custo e tempo

Filtros obrigatorios para um exemplo entrar no silver:

- JSON valido
- aspecto nao generico demais
- opiniao nao vazia
- aspecto e opiniao ancorados no texto por heuristica minima
- sem duplicacao obvia
- sem `aspecto == opiniao`
- sem comentario claramente fora da elegibilidade alvo

---

## 11. Escolha da LLM professora

Este spec nao fixa um unico vendor, mas fixa requisitos.

### 11.1 Requisitos obrigatorios da professora

- suporte forte a PT-BR informal
- boa obediencia a JSON/estrutura
- custo aceitavel para `1.000–5.000` comentarios
- capacidade de abster com qualidade
- disponibilidade operacional para o usuario no Brasil

### 11.2 Papel da professora neste ciclo

Obrigatorio:

- gerar silver labels
- ajudar a descobrir slices de erro

Opcional:

- servir como baseline comparativo no gold set
- servir como fallback em comentarios de baixa confianca do BERT

### 11.3 A professora nao define a arquitetura final sozinha

Mesmo que a professora seja melhor no gold set, isso nao invalida automaticamente o caminho BERT.

O ponto deste ciclo e avaliar se:

- o BERT alcança qualidade util
- o BERT reduz custo e dependencia
- o BERT preserva melhor spans e consistencia operacional

---

## 12. Desenho do treino BERTimbau

### 12.1 Baseline recomendado

Comecar por:

- `neuralmind/bert-base-portuguese-cased`

Migrar para large apenas se:

- o base saturar cedo
- o hardware suportar
- o ganho esperado justificar a complexidade

### 12.2 Tarefa inicial recomendada

O implementador pode escolher uma destas duas formulacoes:

1. **BIO tagging para aspecto e opiniao + classificador de polaridade**
2. **pipeline multi-head inspirado no `dinamica_absa`**

Preferencia deste spec:

- comecar pelo desenho mais simples que permita medir spans de modo confiavel

### 12.3 Reproducibilidade minima

O treino so conta como valido se houver:

- script ou notebook versionado
- config de treino versionada
- seed registrada
- split registrado
- log de metricas por epoca
- checkpoint final identificavel

---

## 13. Benchmark e comparacao

### 13.1 Benchmarks obrigatorios

O branch deve comparar pelo menos:

1. baseline atual do projeto
2. BERTimbau treinado
3. professora usada no silver, se operacionalmente viavel

### 13.2 Medidas obrigatorias no gold set

- `aspect_span_precision`, `aspect_span_recall`, `aspect_span_f1`
- `opinion_span_precision`, `opinion_span_recall`, `opinion_span_f1`
- `pair_f1`
- `polarity_f1`
- `triplet_exact_f1` ou equivalente documentado
- `abstention_precision` em comentarios nao ASTE

### 13.3 Relatorio de slices obrigatorios

O branch deve reportar slices de erro em:

- negacao
- ironia
- pergunta experiencial
- pergunta nao experiencial
- aspecto implicito
- comentario curto/ruidoso

---

## 14. Criterios de aceite

Este ciclo so sera considerado aprovado se todos os criterios abaixo forem atendidos:

1. existe pipeline versionado de criacao de dataset `gold` e `silver`
2. existe gold set pequeno e separado do treino
3. existe treino BERT reproduzivel no repositorio
4. existe comparacao do BERT com pelo menos um baseline do projeto
5. existe recomendacao final sobre promover ou nao o caminho `LLM professora -> BERTimbau`
6. o relatorio final deixa claro o que foi provado e o que continua hipotese

---

## 15. Definition of Done

O branch esta pronto apenas quando entregar:

- dataset spec versionado
- scripts/configs de construcao de dados
- gold set pequeno e auditavel
- silver set inicial gerado
- baseline BERT treinado
- benchmark no gold set
- relatorio final com decisao

Nao basta entregar:

- um notebook solto
- um print de loss
- um checkpoint sem lineage

---

## 16. Riscos conhecidos

### R1. Silver labels podem cristalizar erro da professora

Mitigacao:

- filtros mais duros
- gold set separado
- inspecao de discordancias

### R2. BERT pode aprender bem span e mal pair/polarity

Mitigacao:

- medir tarefas por componente, nao so ASTE final
- permitir arquitetura em etapas

### R3. O branch pode superotimizar para comentarios faceis

Mitigacao:

- gold set estratificado
- slices de dificuldade obrigatorios

### R4. `bert-large` pode ficar caro demais em hardware local

Mitigacao:

- baseline primeiro com `bert-base`
- promocao condicional para large

### R5. O time pode tratar sucesso parcial como fim do problema

Mitigacao:

- relatorio final precisa separar:
  - o que esta pronto para producao
  - o que e apenas baseline promissor

---

## 17. Entregavel final esperado

O branch deve terminar com uma decisao clara em uma destas formas:

1. **promover o caminho BERTimbau**
   - porque o baseline ja demonstrou qualidade suficiente para justificar investimento continuo

2. **manter BERTimbau como prioridade, mas nao como default ainda**
   - porque o pipeline de dados ficou pronto, mas a qualidade ainda nao atingiu o ponto de promocao

3. **adiar o caminho BERTimbau**
   - apenas se o branch provar, com evidencia forte, que o custo de dados e a perda de qualidade inviabilizam o plano neste momento

---

## 18. Prompt de handoff para Claude Opus

Implemente o Ciclo 3A deste repositorio em modo spec-driven.

Leia primeiro:

- `docs/ADRs.md`
- `docs/PLANO_A_BERTIMBAU.md`
- `docs/FINE_TUNING_CICLO.md`
- `docs/SPEC_CICLO_2_VALIDACAO_ASTE_ABSA_HAIKU.md`
- `docs/ARQUITETURA.md`

Sua missao e transformar a tese `LLM professora -> BERTimbau` em um branch tecnicamente auditavel.

Regras obrigatorias:

- nao trate silver labels como verdade final
- crie gold set separado e versionado
- entregue treino BERT reproduzivel
- compare o BERT com pelo menos um baseline existente
- deixe explicito o que foi validado e o que continua hipotese

Voce tem autonomia para:

- escolher `bert-base` ou `bert-large`
- escolher a professora mais adequada operacionalmente
- definir o formato de dataset mais pragmatico
- limitar o primeiro treino a slices mais limpos, se justificar

Mas nao tem permissao para:

- declarar vitoria sem gold set
- relatar somente metricas cosmeticas
- promover o BERT a default sem benchmark minimamente defensavel

O branch precisa sair com uma recomendacao final sobre se `LLM professora -> BERTimbau` deve virar o caminho oficial do projeto.

---

## 19. Referencias externas uteis

- BERTimbau Large: `https://huggingface.co/neuralmind/bert-large-portuguese-cased`
- Hugging Face Datasets Quickstart: `https://huggingface.co/docs/datasets/en/quickstart`
- Hugging Face Transformers token classification: `https://huggingface.co/docs/transformers/tasks/token_classification`
- Hugging Face PEFT: `https://huggingface.co/docs/transformers/peft`
- Hugging Face TRL SFT Trainer: `https://huggingface.co/docs/trl/sft_trainer`
