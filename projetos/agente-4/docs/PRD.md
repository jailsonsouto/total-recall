# PRD — Agente 4: Consumer Intelligence

**Versão:** 1.0
**Data:** Março/2026
**Status:** Fase 1 em andamento (TCC)

---

## 1. Problema

O sistema multi-agente de briefing produz análises sofisticadas de marca (IAM), score preditivo (BVS), análise competitiva e priorização. Mas há uma lacuna estrutural: **nenhum agente ouve a consumidora real antes de o briefing ser escrito.**

O que acontece sem o Agente 4:

- Um PM propõe uma máscara com claim de "reconstrução proteica"
- O Agente 2 prevê BVS 8.4
- O Agente 6 escreve o briefing com esse claim
- O briefing chega ao Comitê
- A gerente de marca do segmento cacheado sinaliza: *"esse claim vai gerar backlash — a comunidade de cacheadas rejeita 'proteína' por causa do efeito rebote"*
- Três semanas de trabalho analítico, nenhuma delas ouviu as 28 menções negativas sobre proteína no corpus do TikTok

O Agente 4 resolve esse problema injetando voz real da consumidora **antes** de qualquer agente rodar.

---

## 2. Objetivos

### Objetivo 1 — Extrair inteligência ASTE por categoria de produto

Para cada briefing, o Agente 4 consulta o corpus e extrai triplas `(aspecto, opinião, polaridade)` relevantes para a categoria. Não apenas "sentimento", mas a expressão exata da consumidora sobre o atributo específico.

### Objetivo 2 — Segmentar por comunidade HNR

A consumidora de produtos capilares não é homogênea. Cacheadas, enroladas e henêgatas têm necessidades, vocabulários e red flags distintos. O Agente 4 pondera os insights por segmento e identifica o segmento dominante para o produto em análise.

### Objetivo 3 — Gerar indicadores acionáveis para o briefing

Não entregar uma lista de sentimentos — entregar métricas que o PM e o Comitê possam usar:
- **PN (Prioridade Negativa)**: dores que o produto deve resolver ou evitar
- **AP (Alavancagem Positiva)**: atributos que geram conversão no segmento
- **Controvérsia**: temas divisórios que exigem cuidado no posicionamento
- **Crescimento**: ingredientes ou claims em ascensão — janelas de oportunidade

### Objetivo 4 — Alimentar a Memória Viva (Agente 8)

Os padrões detectados pelo Agente 4 são persistidos no Agente 8. Com o tempo, o sistema acumula um mapa de "o que a comunidade X pensa sobre a categoria Y" — que se torna mais preciso a cada briefing processado.

---

## 3. Fontes de dados

### 3.1 Corpus primário — TikTok

| Atributo | Valor atual |
|---|---|
| Total de comentários | 4.802 |
| Formato | JSON (schema V1 normalizado) |
| Marcas cobertas | Novex, Elseve, Embelleze, Amend, Haskell |
| Categorias cobertas | Máscara de reconstrução, reposição de massa, cronograma capilar |
| Coleta | Chrome extension + scraper manual |
| Localização | `/COLETA-COMENTARIOS-TIKTOK/PROCESSAMENTO-COLETA/kimi/package/user_input_files/` |

### 3.2 Expansão planejada

| Fonte | Categoria adicional | Prioridade |
|---|---|---|
| TikTok (mais vídeos) | Máscaras de hidratação, séruns | Alta |
| YouTube (comentários) | Reviews longos, tutoriais | Média |
| Beleza na Web (reviews) | Avaliações com estrelas + texto | Média |
| Reddit/grupos FB | Comunidades técnicas de cuidado capilar | Baixa |

### 3.3 Filtragem por relevância para o briefing

O corpus completo é filtrado por `briefing_relevance_score` — similaridade semântica entre o produto do briefing e os comentários do corpus. Apenas comentários com score > 0.6 entram na análise.

---

## 4. Taxonomia de aspectos (Codebook V3 + extensões para briefing)

### Categorias base (Codebook V3 TCC)

| Categoria | Exemplos |
|---|---|
| PRODUTO | máscara, shampoo, condicionador, reposição de massa |
| RESULTADO_EFICÁCIA | funcionou, vi resultado, salvou, não fez diferença |
| TEXTURA_CABELO | seco, quebradiço, elástico, palha, macio, brilho |
| TEXTURA_PRODUTO | textura, cheiro, consistência |
| EMBALAGEM | tamanho, bisnaga, rendimento |
| APLICAÇÃO | tempo de ação, frequência, modo de usar |
| CUSTO | preço, vale a pena, custo-benefício |
| CRONOGRAMA_CAPILAR | hidratação, reconstrução, питanie |
| PRESCRITOR | cabeleireira, influenciador, recomendação |
| CABELO_TIPO | crespo, liso, ondulado, poroso, elástico |

### Categorias adicionadas para o briefing

| Categoria | Por que importa | Exemplos |
|---|---|---|
| ATIVO_INGREDIENTE | Valida/invalida ingredientes do briefing | queratina, murumuru, pantenol, silicone |
| CLAIM_EFICÁCIA | Valida claims que o briefing vai comunicar | "reconstrói", "hidratação de 72h", "sem frizz" |
| CUSTO_PERCEBIDO | Valida posicionamento de preço | "caro", "vale muito", "acessível" |
| ROTINA_CRONOGRAMA | Informa frequência e regime de uso | "uso 1x semana", "entra no cronograma" |

---

## 5. Definição dos indicadores

### PN — Prioridade Negativa

Mede a intensidade e frequência das dores mais citadas em aspectos negativos.

```
PN(aspecto) = (frequência_negativa / total_comentários) × intensidade_média
```

PN alta → aspecto que o produto deve endereçar ou evitar ativamente.

### AP — Alavancagem Positiva

Mede o potencial de conversão de atributos positivos.

```
AP(aspecto) = (frequência_positiva / total_comentários) × score_engajamento_médio
```

AP alta → atributo que deve ser destacado na comunicação do produto.

### Controvérsia

Mede a divisão de opinião sobre um aspecto.

```
Controvérsia(aspecto) = min(pos_ratio, neg_ratio) / max(pos_ratio, neg_ratio)
```

Controvérsia > 0.4 → aspecto divisório, sinalizar para o Comitê.

### Crescimento

Compara frequência do aspecto no último trimestre vs. período anterior.

```
Crescimento(aspecto) = (freq_trimestre_atual - freq_trimestre_anterior) / freq_trimestre_anterior
```

Crescimento > 0.3 → tendência emergente, janela de oportunidade.

---

## 6. Métricas de sucesso

### Métricas do motor ASTE (TCC)

| Métrica | Meta |
|---|---|
| ATE-F1 (extração de aspectos) | ≥ 0.70 |
| OTE-F1 (extração de opiniões) | ≥ 0.65 |
| ASTE-F1 (triplas completas) | ≥ 0.60 |
| Kappa inter-anotador | ≥ 0.75 |

### Métricas de qualidade do Agente 4

| Métrica | Meta |
|---|---|
| Cobertura de categoria (% briefings com corpus relevante) | ≥ 80% |
| Precisão de segmentação HNR (validação manual amostral) | ≥ 75% |
| Alertas de red flag corretos (validação pelo PM) | ≥ 85% |

### Métricas de impacto no sistema

| Métrica | Meta |
|---|---|
| Redução de rejeições por razões evitáveis (ex: claim rejeitado por comunidade) | ≥ 30% em 6 meses |
| Menções ao output do Agente 4 nas decisões do Comitê | > 50% dos briefings |

---

## 7. O que o Agente 4 não faz

- **Não coleta dados** — a coleta é responsabilidade do PM/pesquisador via Chrome extension ou scraper. O Agente consome dados já coletados.
- **Não acessa internet em tempo real** — opera sobre corpus local. Snapshots periódicos, não live data.
- **Não substitui pesquisa qualitativa** — é escuta sistemática, não etnografia profunda. Complementa, não substitui estudos com consumidoras.
- **Não detecta desinformação ou spam** — o corpus assume que comentários orgânicos são vozes reais. Filtros básicos de spam estão no schema (campo `eligibility`), mas sem validação profunda.

---

## 8. Dependências

| Dependência | Tipo | Estado |
|---|---|---|
| BERTimbau fine-tuned (TCC) | Motor analítico | Pendente (depende das 500 anotações) |
| Corpus TikTok JSON (schema V1) | Dados | ✓ Disponível (4.802 comentários) |
| Agente 8 — Memória Viva | Persistência | ✓ MVP implementado |
| LangGraph | Orquestração | Pendente (integração Agente 8 primeiro) |
