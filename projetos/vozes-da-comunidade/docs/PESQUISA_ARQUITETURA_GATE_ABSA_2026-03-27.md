# Pesquisa Profunda: Gate, ABSA e os Objetivos do Agente 4

> **Tipo:** Pausa exploratória e crítica na arquitetura
> **Data:** 2026-03-27
> **Motivação:** A implementação atual do gate descarta 80% do corpus aceito pelo Router.
> Isso levanta a questão: o gate está otimizado para custo de API ou para inteligência?

---

## 1. O que o Agente 4 realmente precisa fazer

Antes de avaliar o gate, é necessário ler o PRD com honestidade.

O objetivo declarado do Agente 4 não é "extrair triplas ASTE". É:

> *"Injetar voz real da consumidora **antes** de qualquer agente rodar."*

O problema concreto que o PRD descreve:

> *"Um PM propõe uma máscara com claim de 'reconstrução proteica'. O briefing chega ao Comitê. A gerente de marca sinaliza: 'esse claim vai gerar backlash — a comunidade de cacheadas rejeita proteína por causa do efeito rebote'. Três semanas de trabalho analítico, nenhuma delas ouviu as 28 menções negativas sobre proteína no corpus do TikTok."*

ASTE é o **método** escolhido para entregar essa inteligência. Mas o objetivo é mais amplo: capturar, estruturar e entregar **o que a consumidora está dizendo**, em todas as formas que isso se manifesta — não apenas quando ela usa aspecto + opinião + polaridade em estrutura textual explícita.

---

## 2. Como o ABSA é usado atualmente

O pipeline atual, do corpus ao output, é:

```
TikTok JSONs (schema V1)
    │
    ▼ Router — filtra por interaction_type + comprimento
    │  Aceita: 1.876 / 4.804 (39%)
    │
    ▼ Gate Semântico — classifica em 4 classes
    │  aste_ready:     383  (20% dos aceitos) ← único caminho com processamento
    │  absa_implicit:  535  (28%)             ← DESCARTADO
    │  claim_question: 337  (18%)             ← DESCARTADO
    │  off_topic:      621  (33%)             ← DESCARTADO
    │
    ▼ Extrator ASTE (sabiazinho-4)
    │  Recebe: 383 comentários
    │  Produz: ~300-350 triplas estimadas (com ~82% de extração)
    │
    ▼ IndicatorCalculator
    │  Agrega por (categoria, segmento)
    │  Calcula: PN, AP, Controvérsia, Crescimento
    │
    ▼ ConsumerIntelligenceOutput
       Persiste no Warm Store → Agente 6 (Briefing Writer)
```

O ABSA no sentido amplo (sentiment analysis sobre aspectos) só acontece na trilha `aste_ready`. As outras três classes — que representam **80% dos comentários aceitos pelo Router** — são descartadas antes de qualquer processamento analítico.

O `IndicatorCalculator` só sabe trabalhar com `ASTETriplet`. Não tem nenhum mecanismo para absorver sinais de sentimento implícito ou necessidades não verbalizadas.

---

## 3. O gate está prejudicando o ABSA?

**Resposta direta: sim, mas de formas diferentes para cada classe.**

### 3.1 `absa_implicit` — sentimento perdido (28% dos aceitos)

Esta é a perda mais significativa para os indicadores.

Da amostra inspecionada, pelo menos dois tipos de comentários caem aqui:

**Tipo A — deveriam ser `aste_ready` (falso negativo do gate):**
- *"máscaras de reconstrução com queratinha deixam meu cabelo fraco, palha e quebradiço"*
  — aspecto: máscara de reconstrução + queratinha | opinião: fraco, palha, quebradiço | polaridade: NEG
  — Classificado como `absa_implicit` porque "fraco", "palha", "quebradiço" não estão nos `_OPINION_ANCHORS` do gate.

- *"eu vou ficar com a elseve, kérastase não cabe no meu bolso"*
  — aspecto: kérastase | opinião: não cabe no meu bolso | polaridade: NEG (custo)
  — Classificado como `absa_implicit` porque "bolso" não é um anchor de opinião.

Estes casos revelam um problema de calibração do gate reconstruído: os `_OPINION_ANCHORS` cobrem vocabulário canônico (amei, horrível, maravilhoso) mas não cobrem metáforas, idiomatismos e vocabulário de textura/resultado específico do domínio capilar.

**Tipo B — genuinamente sem span mas com sinal de AP:**
- *"eu tô usando ela pela terceira vez e tô amando"*
  — Nenhum aspecto explícito, mas o comportamento (uso recorrente = fidelidade) é sinal de AP.
- *"falaaa mesmo amg, eu descobri sobre reposição de massa através de ti"*
  — Endosso de influenciador + descoberta de categoria → sinal de PRESCRITOR relevante.

O calculador atual não consegue absorver esses sinais porque não tem como estruturá-los sem tripla.

### 3.2 `claim_question` — necessidades não atendidas invisíveis (18% dos aceitos)

Esta é a perda mais crítica para o **objetivo de Product Discovery**.

Da amostra:
- *"a reposição de massa da novex realmente funciona? tenho vontade de comprar e ser..."*
  — Dúvida sobre eficácia + intenção de compra frustrada = sinal direto de PN.
  — Um PM que lesse isso saberia: *há demanda, mas há barreira de ceticismo*.

- *"e se não tiver dinheiro como faz?"*
  — Sensibilidade a preço não atendida = dor de CUSTO_PERCEBIDO.

- *"reparação e reconstrução é a mesma coisa?"*
  — Confusão terminológica = sinal de comunicação inadequada no mercado.

- *"acidificação ou reposição de massa?"*
  — Dúvida de protocolo = oportunidade de claim de simplicidade/orientação.

Nenhum desses comentários produz uma tripla ASTE limpa. Mas todos são inteligência de produto valiosa que o Agente 4 deveria capturar e entregar ao briefing.

**Problema estrutural: o `claim_question` atual também mistura coisas distintas:**

Da mesma amostra, junto com as perguntas de produto, aparecem:
- *"você é demais adooooorooooo"*
- *"vc e o maximo!"*
- *"vc ta lindissimo"*

Esses não são perguntas sobre produto — são comentários sociais direcionados ao criador do vídeo. O gate reconstruído os classificou como `claim_question` porque a regex `^\s*(vc|você...)` é ampla demais.

Isso significa que o `claim_question` na implementação atual mistura dois grupos que precisam ser separados antes de qualquer processamento.

### 3.3 `off_topic` — descarte correto (33%)

Da amostra inspecionada, o `off_topic` parece estar funcionando bem. Os comentários classificados aqui são genuinamente sociais/fáticos:
- *"🥰🥰🥰boa noite 😂😂😂"*
- *"eu sou feia ."*
- *"e verdade me segue aí também"*

Estes não têm valor analítico para nenhum objetivo do projeto. O descarte é correto.

---

## 4. A tensão arquitetural central

O gate foi projetado com um único objetivo implícito: **reduzir chamadas de API ao extrator ASTE**. Isso é custo-eficiente, mas cria uma tensão com o objetivo real do projeto.

```
Objetivo do gate atual:       Minimizar custo de API
                              → filtra agressivamente → 80% descartado

Objetivo real do projeto:     Capturar toda a voz da consumidora
                              → precisa processar absa_implicit e claim_question
```

O gate atual resolve um problema de engenharia (custo) mas cria um problema de produto (cobertura de inteligência). Para um corpus de 4.804 comentários e custo total de ~R$ 3,00 sem gate, essa troca pode não fazer sentido.

---

## 5. Proposta: o gate como roteador de trilhas, não como filtro

Em vez de um gate binário (processa / descarta), o Agente 4 pode ter um **roteador de trilhas** com três pipelines paralelos:

```
Corpus aceito pelo Router (1.876 comentários)
    │
    ▼ Gate Roteador
    │
    ├── Trilha ASTE (383 comentários, 20%)
    │   └── sabiazinho-4 → triplas → PN/AP/Controvérsia/Crescimento
    │
    ├── Trilha Social Listening (535 comentários, 28%)  ← absa_implicit
    │   └── classificação de sentimento simples (POS/NEG sem span)
    │       → feed de AP/PN implícito (frequência × sentimento)
    │       → netnografia: padrões de uso recorrente, fidelidade, descoberta
    │
    ├── Trilha Product Discovery (337 comentários, 18%)  ← claim_question
    │   └── extração: (produto_mencionado, tipo_dúvida, frequência)
    │       → PMO/Product Discovery: barreiras, confusões, sinais de demanda
    │
    └── Descartado (621 comentários, 33%)  ← off_topic genuíno
```

### Trilha ASTE (sem mudança)
Igual ao que existe hoje. Produz triplas estruturadas para os indicadores PN/AP/Controvérsia/Crescimento.

### Trilha Social Listening (ABSA_IMPLICIT)
Não precisa de triplas. Precisa de:
- Sentimento geral do comentário (positivo/negativo)
- Produto ou categoria mencionada (se houver)
- Campos netnográficos do schema V1 (`native_terms`, `cultural_markers`, `consumption_stage`)

Output para o briefing:
> *"Além das triplas ASTE, 182 consumidoras expressaram sentimento positivo associado a reposição de massa sem mencionar aspecto específico — possível indicador de satisfação difusa ou lealdade de marca."*

### Trilha Product Discovery (CLAIM_QUESTION)
Esta é a mais valiosa para o objetivo de PMO que o usuário mencionou.

O analista especializado em PMO/Product Discovery lê um corpus de perguntas e vê:
- **Frequência de dúvida por produto/categoria**: quantas perguntas sobre eficácia de reposição de massa vs. cronograma?
- **Tipo de dúvida**: eficácia? modo de usar? preço? comparação?
- **Produto mencionado**: Novex? Elseve? Genérico?

Isso alimenta diretamente o campo `dores_principais` com um tipo de dor diferente: **necessidade não atendida**, em vez de insatisfação com experiência.

Output para o briefing:
> *"**Necessidades não atendidas (Product Discovery):** 47 perguntas sobre eficácia de reposição de massa identificadas. Tipo predominante: ceticismo sobre resultado (72%) + confusão terminológica reposição/reconstrução (18%). Oportunidade de claim de educação + prova social."*

---

## 6. Caminho C em detalhe: claim_question como analista PMO

### O que um analista de PMO faria com essas perguntas

Um analista de Product Discovery treinado, ao ler o corpus de `claim_question`, produziria:

| Sinal | Exemplo | Interpretação para o PM |
|-------|---------|------------------------|
| Ceticismo de eficácia | "realmente funciona?" | Barreira de compra — precisa de prova social ou claim forte |
| Confusão terminológica | "reparação e reconstrução é a mesma coisa?" | Oportunidade de posicionamento por educação |
| Sensibilidade de preço | "e se não tiver dinheiro como faz?" | Segmento price-sensitive — versão econômica ou tamanho trial |
| Demanda com intenção | "tenho vontade de comprar e ser..." | Funil de conversão interrompido — o que falta para converter? |
| Protocolo/rotina | "acidificação ou reposição de massa?" | Consumidora avançada perdida — need for authority positioning |

### O que o extrator de PMO precisa extrair

Estrutura simplificada — não é ASTE, é `ProductSignal`:

```python
@dataclass
class ProductSignal:
    produto_mencionado: str      # "reposição de massa", "novex", "queratina"
    tipo_sinal: str              # "ceticismo_eficacia" | "confusao_conceitual" | "sensibilidade_preco" | "demanda_latente" | "protocolo"
    texto_original: str          # citação direta
    segmento_hnr: str            # se disponível no schema V1
```

A extração pode ser feita por sabiazinho-4 com um prompt diferente, ou por regras simples de classificação. É mais fácil que ASTE porque não exige span extraction — só intenção + produto.

### Output para o briefing

```markdown
### Sinais de Product Discovery (Caminho C)

**Barreiras de compra identificadas (47 ocorrências):**
1. Ceticismo sobre eficácia de reposição de massa — 31 menções
   → *"a reposição de massa da novex realmente funciona?"*
2. Confusão reposição ≠ reconstrução — 8 menções
   → *"reparação e reconstrução é a mesma coisa?"*
3. Sensibilidade a preço — 5 menções

**Implicação para o briefing:** o copy deve incluir prova social explícita e
diferenciação clara do conceito de reposição de massa vs. reconstrução.
```

---

## 7. Como o ABSA_IMPLICIT se encaixa no social listening para marketing

O campo de Netnografia/Social Listening para o marketing é diferente do ASTE para o briefing de produto.

| Dimensão | ASTE (briefing) | Social Listening (marketing) |
|----------|----------------|------------------------------|
| Pergunta que responde | "O que a consumidora diz sobre X?" | "Como a consumidora fala sobre X? Qual é o mood geral?" |
| Output | Triplas estruturadas (aspecto + opinião + polaridade) | Volume, sentimento geral, tendências de vocabulário |
| Granularidade | Alta (span-level) | Baixa-média (comment-level) |
| Uso | Decisão de formulação, claim, posicionamento | Monitoramento de marca, detecção de crises, oportunidades de comunicação |
| Quem usa | PM, formulador, Comitê | Marketing, social media, brand manager |

Os comentários `absa_implicit` alimentam melhor o segundo caso. Exemplos de inteligência que um brand manager extrairia:

- *"eu tô usando ela pela terceira vez e tô amando"* → fidelidade de comportamento, não de discurso
- *"eu descobri sobre reposição de massa através de ti"* → influenciador como canal de descoberta → dado para media strategy
- *"vou fazer essa cor amanhã"* → intenção de compra → momentum de tendência

Nenhum desses é ASTE. Todos são inteligência de marketing.

---

## 8. Avaliação crítica: vale redesenhar agora?

### O que jogar fora vs. o que manter

| Componente | Status | Recomendação |
|------------|--------|-------------|
| Gate como roteador (4 classes) | Funciona bem como estrutura | Manter a estrutura, ampliar o destino das classes |
| `off_topic` → descarte | Correto | Manter |
| `aste_ready` → extrator ASTE | Funciona, mas gate subdimensionado (20% vs 71% esperado) | Melhorar calibração dos anchors |
| `absa_implicit` → descarte | Desperdiça inteligência de marketing | Criar trilha de social listening |
| `claim_question` → descarte | Desperdiça inteligência de PMO | Criar trilha de Product Discovery |
| IndicatorCalculator | Só processa triplas ASTE | Precisa aceitar `ProductSignal` e sentimento implícito no futuro |

### O que fazer agora vs. o que planejar para depois

**Agora (pré-requisito para o próximo run de corpus):**
1. Melhorar os `_OPINION_ANCHORS` e `_ASPECT_ANCHORS` para reduzir falsos negativos em `absa_implicit` — especialmente vocabulário de textura capilar e metáforas de resultado.
2. Separar no `claim_question` os comentários sociais dos comentários de produto (a regex atual é ampla demais).
3. Salvar os três buckets (`absa_implicit`, `claim_question`, `off_topic`) em arquivos separados para inspeção futura — não precisam de processamento agora, mas precisam estar disponíveis.

**Planejado (Ciclo 2 ou posterior):**
1. Trilha Social Listening: classificador de sentimento simples para `absa_implicit`
2. Trilha Product Discovery: extrator de `ProductSignal` para `claim_question`
3. Atualizar `ConsumerIntelligenceOutput` para incluir sinais dessas duas trilhas
4. Atualizar o formatter do Agente 6 para incluir seção "Sinais de Product Discovery"

---

## 9. Perguntas abertas para decisão do usuário

1. **O Agente 4 deve ser apenas um motor ASTE, ou um motor de inteligência de consumidor mais amplo?**
   — O PRD sugere o segundo, mas a implementação atual faz o primeiro.

2. **A trilha de Product Discovery (claim_question) deve ser processada no mesmo batch ou em pipeline separado?**
   — Processar junto (mesmo run) é mais eficiente, mas complica o output. Pipeline separado é mais limpo.

3. **O social listening (absa_implicit) vai para o Agente 6 (briefing) ou para outro consumidor?**
   — O Agente 6 precisa de inteligência acionável para o PM, não de dados brutos de mood.
   — Pode fazer mais sentido para o brand manager / marketing do que para o briefing de produto.

4. **Vale corrigir os `_OPINION_ANCHORS` agora, antes de rodar o corpus?**
   — A calibração atual provavelmente está deixando 15-20% dos verdadeiros `aste_ready` caírem em `absa_implicit`.
   — Um teste manual em 50 amostras de `absa_implicit` responderia isso em 30 minutos.

---

## 10. Recomendação de próximos passos

**Passo imediato (sem custo de API):**
Inspecionar 50 amostras aleatórias de `absa_implicit` e classificar manualmente:
- Quantas são `aste_ready` real? → calibra o gate
- Quantas têm sinal de social listening legítimo? → decide se vale a trilha

**Passo seguinte (antes do run de corpus):**
Salvar os buckets `absa_implicit` e `claim_question` no script `run_corpus.py` como arquivos separados, mesmo que não sejam processados. Custam zero de API e preservam inteligência para análise posterior.

**Passo de médio prazo (Ciclo 2 ou Ciclo 3):**
Implementar o extrator de `ProductSignal` para `claim_question`. Este é o caminho C descrito pelo usuário — é mais simples que ASTE, mais valioso para PMO, e diferencia o Agente 4 de qualquer solução de sentiment analysis genérica.

---

*Documento gerado em 2026-03-27 como pausa crítica antes de decisão sobre o próximo ciclo de desenvolvimento.*
