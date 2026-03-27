# Spec-Driven Development: Ciclo 2 de validacao ASTE/ABSA com gate, 7b e Haiku

## Status

- Estado: proposto
- Data: `2026-03-26`
- Objetivo: reduzir friccao de decisao tecnica no proximo branch
- Leitor principal: Claude Opus ou outro implementador com autonomia

---

## 1. Proposito deste spec

Este documento define o **Ciclo 2** do trabalho sobre ASTE/ABSA no projeto Vozes da Comunidade.

O Ciclo 1 produziu melhoria real, mas tambem deixou uma zona cinzenta:

- ha ganhos de coerencia semantica no pipeline
- ha um benchmark 3-way util entre `qwen2.5:3b`, `qwen2.5:7b` e Haiku
- mas ainda faltam evidencias fortes para transformar o benchmark em decisao final de arquitetura

Este spec existe para evitar o erro mais comum nesta fase:

> confundir acordo entre modelos com verdade, ou confundir melhora narrativa com melhora validada

O implementador tem autonomia tecnica. Em troca, deve seguir as regras deste spec e devolver uma decisao sustentada por evidencia versionada.

---

## 2. Decisao que este ciclo precisa destravar

Ao fim do branch, o projeto precisa sair com uma decisao explicita sobre o proximo estado do ASTE/ABSA.

Essa decisao deve escolher entre quatro caminhos:

1. manter `qwen2.5:3b` como default, com gate + parser + indicadores mais robustos
2. promover `qwen2.5:7b` a default
3. introduzir um backend experimental de extracao via Haiku
4. manter Haiku apenas como benchmark de referencia, sem promover a backend de producao

O branch nao precisa obrigatoriamente entregar uma promocao de modelo. Ele precisa entregar uma **decisao tecnicamente defensavel**.

---

## 3. Linha de base factual atual

As afirmacoes abaixo sao consideradas o baseline confiavel deste spec porque estao suportadas por codigo e artefatos persistidos.

### 3.1 Estado do pipeline

Fatos suportados pelo codigo:

- existe Router operacional
- existe Gate Semantico operacional
- existe parser do SLM com validacoes programaticas
- existe fix de coerencia nos indicadores
- Haiku esta integrado no repositorio como **sintese**, nao como extrator ASTE de producao

Fontes:

- `src/vozes_da_comunidade/batch/gate.py`
- `src/vozes_da_comunidade/batch/pipeline.py`
- `src/vozes_da_comunidade/extractors/slm.py`
- `src/vozes_da_comunidade/indicators/calculator.py`
- `src/vozes_da_comunidade/synthesis/formatter.py`

### 3.2 Resultado do gate no lote n=300

Artefato:

- `data/teste_gate_n300.json`

Metricas persistidas:

- `comments_total = 300`
- `comments_accepted = 157`
- `gate_aste_ready = 112`
- `gate_absa_implicit = 23`
- `gate_claim_question = 4`
- `gate_off_topic = 18`
- `triplets_total = 97`
- `elapsed_seconds = 310.3`

Leitura valida:

- o gate reduziu a carga sobre o extrator
- o pipeline ficou mais barato e mais seletivo

Leitura ainda nao validada:

- o gate realmente classificou bem comentario a comentario

Motivo:

o artefato salvo nao preserva as decisoes por comentario. Ele salva resumo agregado e triplas extraidas, mas nao salva a trilha auditavel completa do gate.

### 3.3 Comparativo 3-way em amostra pareada n=112

Artefato principal:

- `data/teste_haiku_matched_n112.json`

Metricas persistidas no arquivo:

- `qwen3b.with_triplet = 97`
- `qwen3b.triplets_total = 97`
- `qwen7b.with_triplet = 29`
- `qwen7b.triplets_total = 40`
- `haiku.with_triplet = 93`
- `haiku.triplets_total = 154`
- `elapsed_seconds = 134.3`
- `estimated_cost_usd = 0.0947`
- `real_parse_errors = 0`

Contagens por grupo, verificadas diretamente no JSON:

- `todos extrairam = 27`
- `3b + Haiku, 7b absteve = 53`
- `so Haiku = 12`
- `so 3b = 17`
- `so 7b = 1`
- `7b + Haiku, sem 3b = 1`
- `todos abstiveram = 1`

Leitura valida:

- o `7b` esta muito mais abstentivo do que o `3b`
- o Haiku extrai em volume proximo ao `3b`, mas com mais triplas por comentario
- existe uma zona grande de discordancia entre modelos

Leitura ainda nao validada:

- que Haiku seja "verdade"
- que os 17 casos `so 3b` sejam todos alucinacao
- que os 12 casos `so Haiku` sejam todos corretos

Motivo:

o benchmark e forte como comparacao entre modelos, mas ainda nao e gold truth.

### 3.4 Rodada Haiku n=300 que NAO deve ser usada como prova final

Artefato:

- `data/teste_haiku_gate_n300.json`

Metricas persistidas:

- `comments_accepted = 269`
- `gate_aste_ready = 191`
- `with_triplet = 128`
- `without_triplet = 63`
- `parse_errors = 63`

Interpretacao oficial deste spec:

este artefato e util como historico de debugging, mas **nao deve ser usado como base final de comparacao com 3b ou 7b** porque:

- nao esta no mesmo subconjunto do benchmark pareado
- foi produzido antes do ajuste de parse para Haiku
- mistura erro de parser com comportamento semantico do modelo

### 3.5 Estado do uso de Haiku no produto

Fato importante:

no repositorio atual, Haiku esta integrado em `formatter.py` para **sintese da secao de inteligencia**, nao como backend ASTE formal do pipeline.

Logo:

- Haiku-extractor ainda e um experimento
- qualquer decisao de promovelo a backend precisa entrar no repositorio de forma versionada
- scripts em `/tmp` nao bastam como implementacao oficial

---

## 4. Problema do Ciclo 2

O problema deste ciclo nao e "fazer mais um benchmark". O problema e **produzir base suficiente para uma decisao de arquitetura com baixa ambiguidade**.

Hoje ha tres friccoes principais:

1. **friccao epistemica**
   - o benchmark 3-way e forte, mas ainda nao ha gold set versionado

2. **friccao de reprodutibilidade**
   - parte do fluxo do Haiku extractor ainda depende de script fora do repo

3. **friccao de auditabilidade**
   - o gate se declara auditavel, mas o JSON persistido nao guarda a decisao por comentario

Se essas tres friccoes nao forem tratadas, o proximo branch corre o risco de:

- promover um modelo cedo demais
- descartar um modelo cedo demais
- ou escrever um relatorio mais forte do que a evidencia suporta

---

## 5. Objetivo formal do Ciclo 2

O branch deste ciclo deve:

1. transformar o benchmark atual em um processo versionado e reproduzivel
2. produzir um gold set pequeno, mas forte o suficiente para decisao
3. auditar o gate comentario a comentario
4. decidir, com base em evidencia, o papel de `3b`, `7b` e Haiku

O branch so sera considerado completo se responder:

> Qual backend deve ficar como default, qual deve ficar como experimental, e por que?

---

## 6. Regras metodologicas obrigatorias

Estas regras sao vinculantes. O implementador pode escolher o desenho tecnico, mas nao pode descumprir estas restricoes sem registrar justificativa forte.

### RM-1: nao usar acordo entre modelos como verdade final

Inter-model agreement e um sinal util, mas nao substitui anotacao humana.

### RM-2: nao usar `teste_haiku_gate_n300.json` como prova comparativa final

Ele pode aparecer como historico de tentativa anterior, mas nao como evidencia principal para decidir entre modelos.

### RM-3: nao declarar "modelo melhor" sem amostra adjudicada manualmente

Pode ser gold set pequeno. Nao precisa ser dataset academico grande. Mas precisa existir.

### RM-4: nao promover Haiku extractor a feature oficial se continuar fora do repositorio

Se Haiku extractor for escolhido, o backend precisa ser implementado e versionado no repo.

### RM-5: nao declarar o gate "auditavel" sem persistir a decisao por comentario

Resumo agregado nao basta.

### RM-6: nao otimizar para contagem de triplas

Mais triplas nao significa melhor ASTE. O alvo e sinal util e coerencia semantica.

---

## 7. Escopo do Ciclo 2

### Em escopo

- versionar o benchmark de comparacao entre modelos
- persistir as decisoes do gate por comentario
- criar um gold set estratificado
- auditar casos de discordancia entre `3b`, `7b` e Haiku
- revisar se o `7b` esta conservador por prompt, parser, threshold ou por capacidade real
- decidir o papel do Haiku extractor
- documentar a decisao final

### Fora de escopo

- fine-tuning completo do BERTimbau
- redesenho amplo do dominio HNR
- reescrita total do pipeline
- perseguir cobertura total do corpus
- fazer claims academicos de SOTA

---

## 8. Hipoteses permitidas

O implementador pode testar uma ou mais hipoteses abaixo. A escolha precisa ser registrada.

### H1: o gate melhorou o pipeline, mas sua qualidade ainda esta submedida

Premissa:

o gate provavelmente esta ajudando, mas nao ha auditoria persistida suficiente para medir precision e recall da sua classificacao.

### H2: o `7b` nao e pior que o `3b`; ele esta apenas calibrado para abstencao excessiva

Premissa:

parte da diferenca pode vir de prompt, threshold, parser ou criterio de validacao, e nao apenas da qualidade do modelo.

### H3: Haiku e a melhor referencia pratica atual, mas ainda nao e oracle

Premissa:

Haiku parece o benchmark mais forte entre os tres, mas ainda precisa ser adjudicado contra gold set.

### H4: parte do erro residual do `3b` ainda vem de parser sem ancoragem textual

Premissa:

o hardening atual melhora muito, mas ainda nao impede alguns casos semanticamente fracos porque nao verifica aderencia ao comentario original.

### H5: a decisao correta e manter Haiku como benchmark e nao como backend

Premissa:

o custo e baixo, mas o ganho de integra-lo como extrator oficial talvez nao compense a complexidade operacional neste momento.

### H6: a decisao correta e introduzir Haiku extractor experimental no repo

Premissa:

se o gold set confirmar vantagem clara, vale manter Haiku como backend opcional ou baseline de alta qualidade.

---

## 9. Trabalho obrigatorio do branch

O branch deste ciclo precisa entregar os itens abaixo.

### T1. Benchmark versionado dentro do repositorio

O fluxo que produz comparacao entre modelos deve existir em codigo versionado.

Aceito:

- script em `scripts/`
- comando CLI
- modulo em `src/`

Nao aceito como estado final:

- dependencia exclusiva de script em `/tmp`

### T2. Persistencia das decisoes do gate

Cada comentario processado pelo gate deve poder ser auditado com:

- `comment_id`
- texto
- classe do gate
- motivo da classe
- se foi enviado ou nao ao extrator

Idealmente tambem:

- interaction_type
- speaker_role
- sinais linguisticos relevantes

### T3. Gold set estratificado

Criar um gold set pequeno, mas informativo.

Tamanho minimo recomendado:

- `120` comentarios

Composicao minima obrigatoria:

- todos os `17` casos `so 3b`
- todos os `12` casos `so Haiku`
- os `2` casos em que `7b` extrai e `3b` nao
- o `1` caso `todos abstiveram`
- pelo menos `20` casos do grupo `3b + Haiku`
- pelo menos `20` casos do grupo `todos extrairam`
- pelo menos `30` comentarios do lote n=300 filtrados pelo gate para classes nao `ASTE_READY`

Cada item do gold set deve ter:

- rotulo de elegibilidade ASTE: `SIM` ou `NAO`
- se `SIM`, triplas esperadas ou aceitaveis
- observacao curta de por que e um caso dificil ou facil

### T4. Auditoria manual dos grupos de discordancia

O branch deve produzir avaliacao manual dos grupos:

- `so 3b`
- `so Haiku`
- `3b + Haiku, 7b absteve`
- `7b extraiu sem 3b`

O objetivo nao e rotular tudo do corpus. O objetivo e responder:

- onde o `3b` esta realmente alucinando
- onde o `7b` esta realmente subextraindo
- onde Haiku esta realmente agregando valor

### T5. Decisao final sobre papel do Haiku

Ao fim do branch, deve existir uma decisao clara:

- `benchmark only`
- `backend experimental`
- `backend recomendado`
- `nao recomendado`

Essa decisao deve ser sustentada por:

- gold set
- benchmark versionado
- custo operacional
- risco de manutencao

---

## 10. Protocolos de validacao obrigatorios

### PV-1: validacao do gate

Avaliar o gate em dois niveis:

1. binario
   - `ASTE_READY` vs `NAO_ASTE`

2. multiclasses
   - `ASTE_READY`
   - `ABSA_IMPLICIT`
   - `CLAIM_QUESTION`
   - `OFF_TOPIC`

Metricas minimas:

- precision por classe
- confusion summary
- exemplos de erro por classe

Se multiclasses for caro demais no primeiro ciclo, o binario e obrigatorio.

### PV-2: validacao dos extratores

Comparar `3b`, `7b` e, se mantido, Haiku no mesmo conjunto.

Metricas minimas:

- comentarios com tripla
- abstencao
- triplas totais
- precisao manual por comentario
- taxa de falso positivo evidente
- qualidade de aspecto
- qualidade de polaridade

### PV-3: validacao de indicadores

Mesmo que o foco principal seja extracao, o branch deve revalidar:

- se `dores` so contem aspectos `NEG` ou `MIX`
- se `atributos` so contem aspectos `POS` ou `MIX`
- o que acontece em empate de polaridade dominante

Se o empate continuar implicito, isso deve ser registrado como risco residual.

### PV-4: validacao de reproducao

O implementador deve deixar claro:

- qual comando gera cada benchmark
- quais inputs foram usados
- em que arquivos o resultado foi salvo

Sem isso, o branch nao e reprodutivel o suficiente.

---

## 11. Criterios de aceite

O branch sera aceito se entregar todos os itens abaixo.

### CA-1: reducao de ambiguidade

Ao fim do branch, deve estar claro se:

- o `3b` continua defensavel
- o `7b` merece promocao
- Haiku deve ou nao entrar como backend

Se a resposta for "ainda nao da para decidir", isso so e aceitavel se vier acompanhada de:

- gold set pronto
- benchmark reprodutivel
- diagnostico objetivo do que ainda falta

### CA-2: evidencia versionada

As evidencias principais devem estar em arquivos do repo, nao em memoria oral ou script temporario.

### CA-3: claims proporcionais a evidencia

Nao serao aceitas conclusoes do tipo:

- "Haiku e o melhor modelo"
- "3b alucina 15%"
- "7b e inutil"

sem que essas frases estejam respaldadas por anotacao humana ou formuladas como inferencia limitada.

### CA-4: auditabilidade real do gate

O gate deve poder ser inspecionado comentario a comentario nos artefatos persistidos.

### CA-5: recomendacao executavel

O branch deve fechar com uma recomendacao concreta, por exemplo:

- manter `3b` agora e usar Haiku so como benchmark
- promover `7b` apos ajuste X
- criar backend `haiku_extractor` em modo experimental

Nao basta entregar um relatorio sem decisao.

---

## 12. Niveis de evidencia aceitos

Este spec define uma hierarquia de confianca para evitar confusao.

### Nivel A: codigo + artefato persistido + validacao manual

Maior peso. Serve para decisao.

### Nivel B: codigo + artefato persistido sem validacao manual

Bom para diagnostico, insuficiente para proclamacao forte.

### Nivel C: relatorio narrativo sem trilha completa nos dados

Util como contexto, insuficiente como prova final.

Aplicacao imediata:

- `teste_haiku_matched_n112.json` = Nivel B
- `AUDITORIA_3WAY_...md` = Nivel C enquanto a coluna `Veredicto` continuar vazia
- benchmark pareado + gold set adjudicado = Nivel A

---

## 13. Ordem recomendada de implementacao

Para reduzir atrito e evitar retrabalho, recomenda-se esta ordem.

### Etapa 1: congelar baseline e mover harness para o repo

Entregas:

- script/comando versionado para reproduzir benchmark pareado
- README curto ou doc de uso

### Etapa 2: tornar o gate realmente auditavel

Entregas:

- output com decisao por comentario
- motivo persistido

### Etapa 3: montar gold set estratificado

Entregas:

- arquivo de anotacao versionado
- criterio de anotacao curto e explicito

### Etapa 4: adjudicar discordancias

Entregas:

- tabela de resultados por grupo
- exemplos representativos corretos e incorretos

### Etapa 5: tomar decisao de arquitetura

Entregas:

- recomendacao final
- impactos de custo
- riscos residuais

---

## 14. Decisoes que o implementador pode tomar sem consultar

O implementador tem autonomia para:

- escolher formato do gold set
- escolher caminho de codigo do harness
- escolher se a comparacao final sera por comentario ou por tripla
- escolher se Haiku vira backend experimental no mesmo branch
- ajustar prompts, thresholds e validacoes se isso fizer parte da hipotese principal

Desde que:

- tudo seja registrado
- o baseline atual nao seja apagado sem comparacao

---

## 15. Decisoes que NAO devem ser tomadas sem evidencia forte

Estas decisoes exigem prova mais dura.

- trocar o default de producao para Haiku extractor
- descartar `7b` definitivamente
- declarar o gate "resolvido"
- declarar que parser hardening atual ja basta

---

## 16. Riscos conhecidos que devem aparecer no relatorio final

O branch deve comentar explicitamente estes riscos, mesmo que nao os resolva.

### R1. Haiku extractor ainda nao e parte organica do pipeline

Sem backend versionado, o benchmark de Haiku continua sem lastro de manutencao.

### R2. Empate em polaridade dominante ainda pode distorcer indicadores

O fix atual resolve o caso mais grave, mas empate e agregacao continuam exigindo definicao explicita.

### R3. Gate pode estar ajudando, mas ainda sem precision auditada

Sem anotacao das classes do gate, ainda nao ha prova forte de desempenho do filtro.

### R4. Parser ainda nao usa ancoragem textual real

Alguns falsos positivos semanticamente fracos ainda podem sobreviver.

### R5. HNR continua subotimo

Nao e foco deste ciclo, mas pode contaminar interpretacao downstream por segmento.

---

## 17. Entregaveis obrigatorios

No minimo, o branch deve devolver:

- codigo alterado
- harness versionado de benchmark
- gold set versionado
- artefatos de saida do benchmark
- relatorio final do Ciclo 2
- decisao tecnica explicita

Idealmente tambem:

- comparacao antes/depois por comentario
- resumo executivo para decisor nao tecnico

---

## 18. Definition of Done

Este branch esta pronto quando:

1. o benchmark `3b vs 7b vs Haiku` pode ser reproduzido a partir do repo
2. o gate pode ser auditado comentario a comentario
3. existe um gold set estratificado versionado
4. as discordancias principais entre modelos foram adjudicadas manualmente
5. existe recomendacao final sobre `3b`, `7b` e Haiku
6. essa recomendacao e proporcional ao nivel de evidencia disponivel

---

## 19. Prompt de handoff para Claude Opus

O texto abaixo pode ser usado diretamente:

```text
Implemente o Ciclo 2 de validacao ASTE/ABSA deste repositorio em modo spec-driven.

Leia obrigatoriamente:
- docs/SPEC_CICLO_2_VALIDACAO_ASTE_ABSA_HAIKU.md
- docs/RESULTADO_BRANCH_GATE_SEMANTICO_2026-03-26.md
- docs/AUDITORIA_3WAY_3b_7b_haiku_n112_2026-03-26.md
- docs/CONCILIACAO_DIAGNOSTICO_CODEX_OPUS_ASTE_ABSA_2026-03-26.md
- data/teste_gate_n300.json
- data/teste_3b_gate_n300_full.json
- data/teste_7b_gate_n300.json
- data/teste_haiku_matched_n112.json

Sua missao nao e apenas melhorar o pipeline. Sua missao e reduzir a ambiguidade tecnica e tomar uma decisao defensavel sobre o papel de 3b, 7b e Haiku.

Regras:
- nao trate acordo entre modelos como verdade final
- nao use teste_haiku_gate_n300.json como prova comparativa final
- nao promova Haiku extractor a feature oficial se ele continuar fora do repo
- nao diga que um modelo e melhor sem base manual minimamente adjudicada
- nao otimize para quantidade de triplas

Entregue:
- benchmark versionado no repo
- gate auditavel por comentario
- gold set estratificado
- auditoria manual dos grupos de discordancia
- recomendacao final sobre backend default e backend experimental

Voce tem autonomia tecnica para decidir implementacao, mas deve obedecer os criterios de aceite do spec.
```

---

## 20. Veredito operacional deste spec

O Ciclo 1 foi suficiente para sair de intuicao pura e entrar em benchmark.

O Ciclo 2 deve sair de benchmark e entrar em decisao.

Se o branch entregar apenas mais uma rodada de numeros sem gold set, sem gate auditavel e sem decisao final, este spec deve ser considerado **nao atendido**.
