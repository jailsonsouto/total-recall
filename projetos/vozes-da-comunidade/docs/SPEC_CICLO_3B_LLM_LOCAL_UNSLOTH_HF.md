# Spec-Driven Development: Ciclo 3B — LLM open/local com Unsloth + Hugging Face

## Status

- Estado: proposto
- Data: `2026-03-27`
- Objetivo: decidir se um LLM open/local fine-tuned pode virar o extrator principal ASTE/ABSA
- Leitor principal: Claude Opus ou outro implementador com autonomia

---

## 1. Proposito deste spec

Este documento define o **Ciclo 3B** do trabalho sobre ASTE/ABSA no projeto Vozes da Comunidade.

O objetivo deste ciclo nao e provar que "LLM e melhor que BERT" em abstrato. O objetivo e responder esta pergunta pratica:

> Um LLM open/local fine-tuned, treinado com stack `Unsloth + Hugging Face`, consegue substituir de forma defensavel o atual SLM zero-shot e aproximar a qualidade de uma professora forte, mantendo custo local baixo?

Este spec trata o caminho open/local como um **cenario alternativo e operacional**:

- mais flexivel que um encoder puro
- mais barato em producao do que API paga
- potencialmente mais generalista que BERT
- mas tambem mais suscetivel a drift, alucinacao e custo de inferencia

---

## 2. Decisao que este ciclo precisa destravar

Ao fim do branch, o projeto precisa sair com uma decisao explicita sobre estas questoes:

1. vale investir em um **LLM open/local fine-tuned** como extrator principal?
2. qual familia deve ser a base do experimento:
   - `Qwen3-8B`
   - `Qwen3-14B`
   - `Qwen2.5-7B/14B` como fallback de estabilidade
3. qual stack deve ser o padrao:
   - `Unsloth` como runtime de treino
   - `Hugging Face` como stack de dados, treino e avaliacao
   - ambos combinados
4. o caminho open/local deve ser:
   - default de producao
   - backend opcional
   - apenas trilha experimental

O branch nao precisa entregar o melhor modelo do mundo. Ele precisa entregar um **baseline open/local reproduzivel e comparavel**.

---

## 3. Linha de base factual atual

### 3.1 O repositorio ja tem um Plano B para SLM local

Fontes:

- `docs/PLANO_B_SLM.md`
- `docs/FINE_TUNING_CICLO.md`

Fatos aceitos:

- o projeto ja contempla SLM local como plano de arranque e fallback
- a familia Qwen ja esta no repertorio do projeto
- o projeto ja reconhece que zero-shot por prompt sozinho nao basta como estrategia final

### 3.2 O ciclo anterior mostrou limites importantes do SLM zero-shot

Fontes:

- `docs/SPEC_CICLO_2_VALIDACAO_ASTE_ABSA_HAIKU.md`
- relatorios derivados do benchmark 3-way

Fatos aceitos:

- `qwen2.5:3b` foi agressivo demais
- `qwen2.5:7b` foi abstentivo demais em parte dos testes
- parser hardening e gate melhoraram bastante, mas nao resolveram tudo

Leitura importante:

- o problema nao e apenas "usar Qwen"
- o problema tambem e usar Qwen **sem treino especifico do dominio**

### 3.3 O caminho open/local atual nao deve ser avaliado so por prompting

Se a hipotese deste ciclo e que um open LLM pode competir melhor, a forma correta de testar nao e so:

- trocar prompt
- trocar quantizacao
- trocar `3b` por `7b`

O teste correto e:

- escolher uma familia
- fine-tunar de forma reproduzivel
- avaliar com gold set separado

### 3.4 Unsloth e Hugging Face sao stack complementar, nao alternativas excludentes

Fatos documentados externamente:

- o Unsloth se posiciona como stack de fine-tuning com ganho de velocidade e reducao de VRAM
- o Hugging Face oferece Hub, Datasets, Transformers, PEFT e TRL
- o proprio ecossistema mostra integracao entre eles

Leitura oficial deste spec:

- **Unsloth** = acelerador/runtime/UI de treino para open LLM
- **Hugging Face** = espinha dorsal de dataset, treino, versionamento e avaliacao

---

## 4. Hipotese central deste ciclo

### H1: o melhor caminho open/local para o projeto nao e zero-shot; e fine-tuning leve de um LLM open

Racional:

- o projeto ja viu o teto do prompting puro em modelos pequenos
- LoRA/QLoRA pode internalizar padrao de rotulacao, abstencao e schema
- isso pode reduzir parse drift e super-extracao

### H2: a familia Qwen e o ponto de partida mais coerente para PT-BR informal e JSON estruturado

Racional:

- o projeto ja tem historico com Qwen
- Qwen2.5 ja demonstrou utilidade operacional no repositorio
- Qwen3 declara suporte forte a multilingual instruction-following

### H3: Unsloth reduz a friccao de treino, mas nao substitui governanca de dados

Sem dataset separado e sem benchmark serio, fine-tuning rapido vira apenas overfitting mais eficiente.

### H4: um LLM open/local fine-tuned pode ser mais geral que BERT, mas tende a continuar pior em spans estritos

Este ciclo deve medir esse trade-off, nao varre-lo para baixo do tapete.

---

## 5. Objetivo formal do Ciclo 3B

O branch deste ciclo deve:

1. escolher uma familia open/local para experimento serio
2. definir o formato de dataset instruction-following oficial para ASTE/ABSA
3. treinar um baseline com `Unsloth + Hugging Face`
4. avaliar esse baseline no mesmo gold set usado pelo projeto ou em gold set comparavel
5. comparar com:
   - baseline zero-shot vigente
   - referencia forte usada como professora, se possivel
6. decidir o papel do open/local fine-tuned na arquitetura

O branch so sera considerado completo se responder:

> O projeto deve promover um LLM open/local fine-tuned como extrator principal, como backend opcional, ou apenas como trilha experimental?

---

## 6. Escopo

### Em escopo

- escolha da familia de modelo
- pipeline de dataset para instruction tuning
- fine-tuning LoRA/QLoRA
- benchmark comparativo
- export do modelo/adapters para uso local
- decisao sobre papel arquitetural

### Fora de escopo

- comparar cinco familias ao mesmo tempo
- construir interface final de produto
- resolver todo o problema de ASTE apenas por prompt
- treinar modelo proprietario do zero
- misturar este ciclo com o Plano A no mesmo branch sem justificativa forte

---

## 7. Regra principal deste cenario

Este spec e um **caminho alternativo** ao Ciclo 3A.

O implementador pode:

- reusar o mesmo gold set do Ciclo 3A para manter comparabilidade

Mas nao deve:

- misturar num unico branch os dois cenarios sem separar claramente os resultados

Se ambos forem implementados, cada um precisa sair com relatorio proprio.

---

## 8. Arquitetura alvo

```text
Corpus / comentarios elegiveis
  ->
Router + Gate
  ->
dataset instruction-following
  ->
gold + silver separados
  ->
fine-tuning open LLM com Unsloth
  ->
avaliacao com stack Hugging Face / scripts versionados
  ->
export adapter ou modelo quantizado
  ->
uso local via Ollama / MLX / transformers
  ->
decisao de promocao ou nao
```

---

## 9. Escolha da familia de modelo

### 9.1 Regra de selecao

O branch deve escolher **uma familia principal**.

Preferencia deste spec:

1. `Qwen3-8B`
2. `Qwen3-14B`, se hardware e custo permitirem
3. `Qwen2.5-7B` ou `Qwen2.5-14B` apenas se a stack, o hardware ou a estabilidade de output tornarem isso mais pragmatico

### 9.2 Justificativa da preferencia

Base oficial externa:

- Qwen3 declara suporte a `100+` idiomas e dialetos com forte instruction-following multilíngue
- Qwen2.5 continua relevante por maturidade operacional e boa reputacao em structured outputs

### 9.3 Proibicao metodologica

Nao e permitido neste ciclo:

- testar varias familias pequenas e publicar apenas a melhor
- trocar de modelo no meio sem registrar a decisao

O branch precisa de uma historia causal clara.

---

## 10. Stack tecnica obrigatoria

### 10.1 Papel do Unsloth

Usar Unsloth quando o objetivo for:

- reduzir VRAM
- acelerar treino
- fazer LoRA/QLoRA de forma mais simples
- exportar adapters/modelos para uso local

### 10.2 Papel da Hugging Face

Usar Hugging Face para:

- carregar e versionar datasets
- preprocessing
- tokenizer e modelo base
- PEFT
- TRL ou trainer equivalente
- avaliacao e reprodutibilidade

### 10.3 Interpretacao oficial deste spec

O branch deve tratar:

- `Unsloth` como **otimizador de treino**
- `Hugging Face` como **infra de dados e modelagem**

Nao tratar como escolha binaria.

### 10.4 AutoTrain

Este spec nao recomenda o `AutoTrain` como peca central do branch.

Se for usado, deve ser apenas auxiliar. O caminho principal deve ser:

- Datasets
- Transformers
- PEFT
- TRL
- Unsloth, se adotado

---

## 11. Especificacao do dataset

### 11.1 Formato de treino

O dataset principal deve ser instruction-following em `jsonl` ou formato equivalente, preservando:

- `comment_id`
- `text_for_model`
- `gate_decision`
- `interaction_type`
- `teacher_source`
- `label_source`
- `triplets`
- `expected_abstain`

### 11.2 Regras de resposta do modelo

O treino deve ensinar explicitamente:

- retornar JSON estruturado
- abster quando nao houver ASTE defensavel
- nao inventar aspecto implicito sem evidencia
- nao confundir comentario social com opiniao de produto

### 11.3 Separacao de conjuntos

Obrigatorio:

- `train`
- `validation`
- `gold_test`

Nao e permitido:

- treinar e avaliar no mesmo conjunto
- usar apenas loss de treino como criterio de sucesso

---

## 12. Hardware alvo e restricoes

### 12.1 Alvo primario

O branch deve declarar explicitamente qual ambiente esta sendo visado:

- `Apple Silicon local`
- `Colab/CUDA`
- `GPU remota`

### 12.2 Regra de pragmatismo

Se o hardware real do projeto for restrito, o branch deve priorizar:

- `8B` quantizado
- LoRA/QLoRA
- reproducibilidade local

em vez de:

- perseguir modelo maior que nao pode ser operado de forma sustentavel

### 12.3 Export operacional

Ao fim do branch, o modelo/adapters precisam ter caminho claro para um dos alvos:

- Ollama
- MLX
- GGUF/llama.cpp
- transformers local

---

## 13. Regras metodologicas obrigatorias

### RM-1: zero-shot nao e baseline suficiente

O branch deve comparar:

- modelo base sem treino
- modelo fine-tuned

Caso contrario, nao sera possivel atribuir ganho ao fine-tuning.

### RM-2: medir qualidade semantica e obediencia estrutural

Metricas obrigatorias:

- taxa de JSON valido
- taxa de schema valido
- `aspect_span_f1` ou metrica aproximada documentada
- `opinion_span_f1` ou equivalente
- `pair_f1`
- `polarity_f1`
- `triplet_exact_f1` ou equivalente
- `abstention_precision`

### RM-3: gold set separado continua obrigatorio

Mesmo no caminho open/local, o gold set nao pode ser pulado.

### RM-4: o branch deve reportar custo operacional real

O relatorio final deve trazer, no minimo:

- tempo de treino
- memoria/VRAM usada
- latencia aproximada de inferencia
- tamanho do adapter/modelo exportado

### RM-5: o branch deve reportar trade-off com BERT, mesmo sem implementar o Plano A

O relatorio precisa explicitar:

- onde o LLM local ganha de um encoder
- onde ele perde
- se o ganho de generalizacao justifica a perda potencial de precisao de span

---

## 14. Tarefas obrigatorias

### T1. Escolha formal da familia de modelo

Entregar:

- modelo escolhido
- motivo da escolha
- motivo de descarte das alternativas proximas

### T2. Dataset instruction-following versionado

Entregar:

- script de conversao
- schema do dataset
- exemplos de treino, validacao e teste

### T3. Receita de fine-tuning reproduzivel

Entregar:

- script ou notebook versionado
- hiperparametros
- seed
- formato de LoRA/QLoRA
- target modules, se aplicavel

### T4. Baseline sem treino

Entregar:

- benchmark do modelo base no gold set

### T5. Baseline fine-tuned

Entregar:

- benchmark do modelo treinado no mesmo gold set

### T6. Export operacional

Entregar:

- adapter, checkpoint ou instrucao clara de export
- caminho de inferencia local validado

### T7. Relatorio de decisao

Entregar:

- papel recomendado do LLM open/local
- riscos residuais
- se vale continuar investindo ou nao

---

## 15. Criterios de aceite

Este ciclo so sera considerado aprovado se todos os pontos abaixo forem atendidos:

1. existe um baseline open/local fine-tuned reproduzivel
2. existe comparacao com o baseline zero-shot
3. existe benchmark em gold set separado
4. existe relatorio de custo operacional
5. existe export ou caminho de uso local validado
6. existe recomendacao final sobre o papel do open/local na arquitetura

---

## 16. Definition of Done

O branch esta pronto apenas quando entregar:

- dataset versionado
- receita de treino versionada
- checkpoint ou adapter utilizavel
- benchmark comparativo
- relatorio final com decisao

Nao basta entregar:

- notebook experimental sem lineage
- print de uma inferencia boa
- modelo sem processo de reproducao

---

## 17. Decisoes finais aceitaveis

O branch deve terminar em uma destas saidas:

1. **promover open/local fine-tuned a backend principal**
   - apenas se a qualidade no gold set justificar claramente

2. **manter open/local fine-tuned como backend opcional**
   - se ele melhorar muito sobre zero-shot, mas ainda ficar atras do caminho principal desejado

3. **manter open/local como trilha experimental**
   - se o ganho for pequeno, o custo operacional for alto ou o comportamento continuar instavel

---

## 18. Riscos conhecidos

### R1. O modelo pode aprender formato e nao semantica

Mitigacao:

- usar gold set com slices dificeis
- medir abstencao
- medir spans e nao so JSON valido

### R2. O modelo pode continuar ruim em spans exatos

Mitigacao:

- medir componente por componente
- nao esconder falha sob metrica agregada

### R3. O branch pode virar festival de tuning sem conclusao

Mitigacao:

- uma familia principal
- uma receita principal
- uma decisao final obrigatoria

### R4. O custo de inferencia local pode continuar alto demais

Mitigacao:

- medir latencia e footprint
- exportar para alvo local realista

### R5. O branch pode canibalizar o Plano A sem evidencia suficiente

Mitigacao:

- relatorio final deve comparar este caminho com o raciocinio do BERTimbau
- sem benchmark serio, este ciclo nao pode decretar morte do Plano A

---

## 19. Prompt de handoff para Claude Opus

Implemente o Ciclo 3B deste repositorio em modo spec-driven.

Leia primeiro:

- `docs/PLANO_B_SLM.md`
- `docs/FINE_TUNING_CICLO.md`
- `docs/SPEC_CICLO_2_VALIDACAO_ASTE_ABSA_HAIKU.md`
- `docs/ARQUITETURA.md`
- `docs/ADRs.md`

Sua missao e provar ou refutar, com evidencia versionada, se um LLM open/local fine-tuned pode virar o extrator principal ASTE/ABSA do projeto.

Regras obrigatorias:

- escolha uma familia principal de modelo
- use dataset separado e gold set
- compare base vs fine-tuned
- reporte custo operacional real
- entregue export ou caminho de uso local
- tome uma decisao final clara

Voce tem autonomia para:

- escolher `Qwen3` ou fallback pragmatico da familia `Qwen2.5`
- escolher `Unsloth`, `TRL`, `PEFT` e o desenho exato do treino
- escolher o ambiente de treino mais realista

Mas nao tem permissao para:

- rodar tuning indiscriminado em varios modelos sem historia causal
- relatar apenas JSON valido e chamar isso de qualidade
- declarar sucesso sem benchmark serio

O branch precisa sair com uma recomendacao final sobre se o caminho open/local fine-tuned deve ser principal, opcional ou apenas experimental.

---

## 20. Referencias externas uteis

- Unsloth Studio: `https://unsloth.ai/docs/new/studio`
- Unsloth GitHub: `https://github.com/unslothai/unsloth`
- Qwen3-8B: `https://huggingface.co/Qwen/Qwen3-8B`
- Qwen3-14B: `https://huggingface.co/Qwen/Qwen3-14B`
- Qwen2.5-7B-Instruct: `https://huggingface.co/Qwen/Qwen2.5-7B-Instruct`
- Hugging Face Datasets: `https://huggingface.co/docs/datasets/en/quickstart`
- Hugging Face PEFT: `https://huggingface.co/docs/transformers/peft`
- Hugging Face TRL SFT Trainer: `https://huggingface.co/docs/trl/sft_trainer`
- AutoTrain docs: `https://huggingface.co/docs/autotrain/en/index`
