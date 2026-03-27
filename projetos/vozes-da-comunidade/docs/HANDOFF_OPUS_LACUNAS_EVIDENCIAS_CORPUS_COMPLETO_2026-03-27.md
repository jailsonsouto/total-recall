# Handoff para Claude Code Opus — Lacunas e Evidências do Corpus Completo

**Projeto:** Vozes da Comunidade  
**Data:** `2026-03-27`  
**Objetivo:** transformar os achados do corpus completo em escopo claro para o próximo nível do pipeline

---

## 1. Leitura executiva

O benchmark de modelos está bom o bastante para uma conclusão provisória:

- no slice `ASTE_READY`, `sabiazinho-4` parece o melhor extrator operacional atual

Mas o corpus completo mostra que **essa não é a decisão principal do projeto**.

O problema maior agora não é só “qual modelo extrai melhor”. É:

1. o Router atual está desalinhado com o schema normalizado atual  
2. o Gate ainda perde sinal importante de produto  
3. o bucket `off_topic` não é semanticamente limpo  
4. uma parte relevante do `ASTE_READY` atual está contaminada por comentários encadeados com `[PARENT]/[REPLY]`

Em resumo:

> o próximo branch não deve só “rodar o Sabiazinho”. Ele deve **corrigir a fronteira semântica do pipeline**.

---

## 2. O que foi verificado diretamente no corpus completo

Base analisada:

- `data/corpus_v1/`
- `4.804` comentários
- `4` arquivos normalizados

Leitura feita a partir de:

- `src/vozes_da_comunidade/batch/router.py`
- `src/vozes_da_comunidade/batch/gate.py`
- corpus V1 real

### 2.1 Distribuição real do corpus

Contagens observadas no corpus:

- `short_or_low_information`: `1748`
- `evaluation_or_observation`: `1329`
- `customer_service_or_brand_interaction`: `947`
- `reply_or_conversation`: `298`
- `question_or_information_seeking`: `253`
- `social_or_phatic`: `139`
- `question_or_claim_validation`: `75`
- `comparison_or_evaluation`: `15`

Achado:

- o corpus atual usa majoritariamente os nomes novos de `interaction_type`
- o Router legado ainda não reflete isso plenamente

---

## 3. Achados novos e concretos

### A1. O Router atual está parcialmente desalinhado com o schema V1 atual

Recomputando o comportamento do Router do jeito que o código atual legível sugere:

- `1881` aceitos
- `2923` rejeitados

Se o Router for alinhado explicitamente aos tipos novos do corpus:

- `1654` aceitos
- `3150` rejeitados

Delta principal:

- `227` comentários `reply_or_conversation` entram hoje por fallback de comprimento

Leitura:

- o Router atual não está filtrando apenas por intenção analítica
- ele também está aceitando ruído estrutural por compatibilidade antiga

### A2. O lote `ASTE_READY` atual está contaminado por replies encadeadas

Na recomputação com o gate atual:

- `426` comentários caem em `aste_ready`
- `100` desses são `reply_or_conversation`
- `113` contêm `[PARENT]` ou `[REPLY]`

Isto representa aproximadamente:

- `23,5%` `reply_or_conversation`
- `26,5%` com contexto de thread embutido

Leitura:

- parte do “ASTE bom” atual não é comentário simples
- é comentário enriquecido por contexto de thread concatenado

Consequência:

- o benchmark atual mede uma mistura de:
  - ASTE de comentário isolado
  - ASTE com contexto conversacional

### A3. Os números do relatório precisam de trilha de proveniência

Os números publicados no relatório de sessão e os números recomputados a partir do código atual não coincidem exatamente.

Relatório:

- `1876` aceitos
- gate em `383 / 535 / 337 / 621`

Recomputação a partir do código atual legível:

- `1881` aceitos
- gate em `426 / 691 / 314 / 450`

Leitura:

- é muito provável que os resultados do relatório venham de uma versão distinta do Router/Gate
- isso não é um problema em si
- mas precisa ser explicitado

Conclusão:

- benchmark sem `commit + script + artifact` fechado continua frágil

### A4. `absa_implicit` é semanticamente mais valioso do que o pipeline atual assume

Na recomputação:

- `691` comentários em `absa_implicit`
- `592` com `brand_entities`
- `595` oriundos de `evaluation_or_observation`
- pelo menos `33` com sinal de preço

Além disso, há um gap de vocabulário nas âncoras de opinião do gate. Dentro de `absa_implicit`, aparecem termos de domínio como:

- `hidratou`: `21`
- `encorpou/encorpa`: `15`
- `secou/ressecou`: `7`
- `quebrou/quebradiço`: `5`
- `palha`: `2`

Leitura:

- parte de `absa_implicit` não é “sentimento difuso”
- é **ASTE provável perdido por vocabulário incompleto do gate**

### A5. `claim_question` é mistura útil, não apenas ruído

Na recomputação:

- `314` comentários em `claim_question`
- `277` com `brand_entities`
- `218` com menção de produto por heurística simples
- `181` vindos de `question_or_information_seeking`
- `55` vindos de `question_or_claim_validation`

Leitura:

- esse bucket tem valor claro para Product Discovery
- o problema não é “descartar tudo”
- o problema é “misturar dúvidas reais de produto com meta-conversa de vídeo”

### A6. `off_topic` atual não é um bucket semanticamente limpo

Na recomputação:

- `450` comentários em `off_topic`
- `411` com `brand_entities`
- `432` vindos de `evaluation_or_observation`

Leitura:

- esse bucket está capturando muito comentário que não é off-topic puro
- o nome `off_topic` provavelmente está superestimando a limpeza da classe

Interpretação mais honesta:

- hoje ele significa algo mais próximo de:
  - “sem aspecto/opinião reconhecidos pelo gate”
  - e não necessariamente “sem valor analítico”

---

## 4. O que isso muda na estratégia

O próximo nível do projeto não deve ser:

- apenas trocar modelo
- apenas rodar corpus completo com `sabiazinho-4`

O próximo nível deve ser:

### Eixo 1 — Corrigir fronteira do pipeline

1. alinhar o Router ao schema atual
2. separar comentário simples de comentário encadeado
3. recalibrar o Gate sobre essa nova base

### Eixo 2 — Deixar de tratar o gate como filtro binário

O gate precisa virar roteador de trilhas:

- `ASTE_READY`
- `ABSA_IMPLICIT`
- `CLAIM_QUESTION`
- `OFF_TOPIC_REAL`

### Eixo 3 — Separar as saídas analíticas por objetivo de negócio

- ASTE para formulação/claim/briefing
- Product Discovery para perguntas e barreiras
- Social Listening para sinais implícitos e netnografia

---

## 5. Escopo recomendado para o próximo branch

### 5.1 Obrigatório

1. corrigir o Router para os nomes atuais de `interaction_type`
2. rejeitar ou isolar `reply_or_conversation`
3. salvar a classificação do gate por comentário em artefato persistido
4. recalcular a distribuição completa do corpus após a correção
5. rerodar benchmark no slice `ASTE_READY` limpo

### 5.2 Fortemente recomendado

6. ampliar `_OPINION_ANCHORS` com vocabulário capilar encontrado no corpus
7. ampliar `_ASPECT_ANCHORS` com aliases contextuais relevantes
8. renomear ou refatorar `off_topic` para algo semanticamente mais honesto
9. criar uma trilha experimental `ProductSignal` para `claim_question`

### 5.3 Opcional, mas de alto valor

10. criar uma trilha `ABSA_IMPLICIT` de social listening leve
11. produzir um gold set pequeno para validar Router + Gate

---

## 6. Critérios de aceite do próximo branch

O branch só deve ser considerado bem-sucedido se entregar:

1. um Router alinhado ao schema atual
2. um `ASTE_READY` livre de contaminação estrutural óbvia por replies
3. um gate auditável por comentário
4. uma nova distribuição do corpus com provenance clara
5. um benchmark de extrator no novo slice limpo
6. uma recomendação explícita sobre:
   - o que fica em ASTE
   - o que vira Product Discovery
   - o que vira Social Listening

---

## 7. O que não fazer

### N1. Não promover `sabiazinho-4` como “solução final” antes do rerun com o slice limpo

Hoje ele é a melhor aposta operacional. Mas o slice ainda está contaminado e o gate ainda está subótimo.

### N2. Não tratar `off_topic` como classe semanticamente resolvida

Os dados do corpus completo não sustentam isso.

### N3. Não confundir economia de custo com ganho de inteligência

O custo atual é baixo o suficiente para permitir mais cobertura sem sacrificar o projeto.

### N4. Não deixar o benchmark sem trilha de proveniência

Toda tabela principal deve citar:

- commit
- script
- artefato
- data

---

## 8. Decisão provisória

Minha decisão provisória, a partir do corpus completo, seria:

1. manter `sabiazinho-4` como melhor extrator ASTE atual
2. não fechar a arquitetura só com base nisso
3. tratar o próximo branch como **branch de saneamento semântico do pipeline**
4. só depois decidir o modelo definitivo e o papel das trilhas paralelas

---

## 9. Prompt de handoff para Claude Code Opus

```text
Retomar a partir deste estado:

Projeto:
vozes-da-comunidade

Objetivo atual:
evoluir o pipeline ASTE/ABSA para o próximo nível sem confundir benchmark de modelo com arquitetura correta

Estado verificado:
- o corpus normalizado tem 4.804 comentários
- o Router atual está parcialmente desalinhado com os interaction_type do schema V1 atual
- 227 comentários reply_or_conversation entram por fallback no Router legado
- no gate recomputado, cerca de 23,5% do ASTE_READY vem de reply_or_conversation
- cerca de 26,5% do ASTE_READY contém [PARENT]/[REPLY]
- absa_implicit e claim_question são buckets ricos em sinal de produto
- off_topic não está semanticamente limpo
- sabiazinho-4 continua sendo o melhor extrator operacional no slice ASTE_READY atual

Arquivos-chave:
- docs/RELATORIO_BENCHMARK_SESSAO_2026-03-27.md
- docs/PESQUISA_ARQUITETURA_GATE_ABSA_2026-03-27.md
- src/vozes_da_comunidade/batch/router.py
- src/vozes_da_comunidade/batch/gate.py
- data/corpus_v1/

O que já foi tentado:
- benchmark 5-way de modelos
- gate semântico heurístico
- parser hardening
- fix de indicadores

Bloqueio atual:
o benchmark de extrator está razoável, mas a fronteira semântica do pipeline ainda está errada

Opções em aberto:
1. continuar apenas com ASTE_READY e promover sabiazinho-4
2. corrigir primeiro Router + Gate + slice ASTE e só depois promover modelo
3. já abrir trilhas paralelas para Product Discovery e Social Listening

Recomendação atual:
seguir a opção 2 como passo obrigatório e abrir a opção 3 de forma experimental no mesmo branch ou em branch logo seguinte

Pedido objetivo:
implemente um branch de saneamento semântico do pipeline com:
- Router alinhado ao schema atual
- isolamento de reply_or_conversation
- gate auditável por comentário
- rerun da distribuição completa
- rerun do benchmark no novo ASTE_READY
- proposta concreta para trilha ProductSignal de claim_question
```

