# Roadmap — Vozes da Comunidade

---

## Estágio 0 — Legado (estado anterior)

O sistema multi-agente não tinha escuta de consumidora. Briefings eram gerados sem cruzar com voz real de comunidades. Rejeições por claims inadequados ao segmento eram descobertas apenas no Comitê.

---

## Estágio 1 — MVP operacional [próximo]

**Objetivo:** Construir o agente funcional com o corpus e o framework disponíveis hoje. O MVP roda com Claude Haiku para extração ASTE — quando o TCC entregar o BERTimbau fine-tuned, a qualidade sobe sem mudança de arquitetura.

```
Motor e dados
  ✓ Corpus disponível: 4.802 comentários TikTok (JSON, schema V1)
  ✓ TikTokTextProcessor: gírias PT-BR, emojis, ironia
  ✓ Framework DINAMICA-ABSA: BERTimbau estruturado
  ✗ Importar dinamica_absa como dependência Python
  ✗ Router por interaction_type (filtrar comentários relevantes)
  ✗ Classificador de briefing_relevance_score por categoria

Indicadores e output
  ✗ Calculador PN/AP/Controvérsia/Crescimento por (categoria, segmento)
  ✗ Red flags automáticos (PN alta + aspecto presente no briefing)
  ✗ Formatador de seção "INTELIGÊNCIA DE CONSUMIDOR"
  ✗ Síntese com Claude Haiku (contexto + linguagem do PM)

Memória
  ✗ post_batch_flush: persistir padrões no Warm Store (Agente 8)
  ✗ Busca por (categoria, segmento) na fase online
  ✗ Acúmulo de padrões entre briefings

CLI
  ✗ vozes batch --input <pasta_json>     # processa corpus offline
  ✗ vozes query "máscara de hidratação"  # consulta por categoria
  ✗ vozes status                         # corpus atual, cobertura
```

**Marco:** agente processa um briefing de teste e entrega seção "INTELIGÊNCIA DE CONSUMIDOR" em < 10 segundos.

---

## Estágio 2 — Upgrade de qualidade [paralelo ao TCC]

**Objetivo:** Substituir extração via Claude Haiku pelo BERTimbau fine-tuned quando o TCC o entregar. Troca de uma linha no `.env` — sem mudança de arquitetura.

```
✗ Receber BERTimbau fine-tuned do TCC
✗ Plug-in via abstração EmbeddingProvider (já prevista na arquitetura)
✗ Re-processar corpus com modelo de maior precisão
✗ Validar melhora de qualidade: ATE-F1 antes vs. depois
```

**Marco:** ASTE-F1 ≥ 0.60 no corpus de validação, sem reescrever código do agente.

---

## Estágio 3 — Integração LangGraph [após Agente 8 conectado]

**Objetivo:** Tornar o Vozes da Comunidade um nó do grafo multi-agente, integrado ao fluxo de briefing.

```
✗ Nó LangGraph do Vozes da Comunidade
✗ Recebe estado do briefing (produto, categoria, segmento alvo)
✗ Injeta "consumer_intelligence" no BriefingState
✗ Output flui para Agente 5 (RICE) e Agente 6 (Briefing Writer)
✗ Red flags bloqueantes: se PN > threshold, alerta antes do Agente 6
✗ Feedback loop: Committee Flush do Agente 8 retroalimenta os padrões
```

**Marco:** briefing completo gerado com seção de Consumer Intelligence integrada automaticamente, sem intervenção manual do PM.

---

## Estágio 4 — Expansão de cobertura [roadmap: 6+ meses]

**Objetivo:** Ampliar cobertura de categorias, segmentos e fontes.

```
Novas fontes de dados
  ✗ YouTube: comentários de reviews longos (mais argumentativos)
  ✗ Beleza na Web: reviews com estrelas + texto (contexto de compra)
  ✗ Corpus multilíngue: PT-BR + ES (mercado hispânico)

Novas categorias de produto
  ✗ Séruns e finalizadores
  ✗ Coloração (segmento tintura)
  ✗ Shampoos low poo / no poo

Modelo
  ✗ Continuous learning: atualização mensal automática com novos comentários
  ✗ Active learning: identifica comentários incertos → fila de anotação humana
  ✗ Detecção automática de novos aspectos emergentes (sem dicionário)
```
