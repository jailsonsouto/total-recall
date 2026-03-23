# Roadmap — Vozes da Comunidade

---

## Estágio 0 — Legado (estado anterior)

O sistema multi-agente não tinha escuta de consumidora. Briefings eram gerados sem cruzar com voz real de comunidades. Rejeições por claims inadequados ao segmento eram descobertas apenas no Comitê.

---

## Estágio 1 — Motor ASTE (TCC) [em andamento]

**Objetivo:** Construir e validar o motor analítico que alimentará o Agente 4.
**Responsável:** TCC MBA DSA USP/ESALQ — Jailson de Castro de Souto
**Código:** `COLETA-COMENTARIOS-TIKTOK/PROCESSAMENTO-COLETA/kimi/`

```
✓ Corpus coletado: 4.802 comentários TikTok (JSON, schema V1)
✓ Codebook V3 para anotação humana (dupla codificação + Kappa)
✓ TikTokTextProcessor (normalização gírias + emojis + ironia)
✓ Framework DINAMICA-ABSA estruturado (BERTimbau, 4 camadas)
✓ Indicadores definidos: PN, AP, Controvérsia, Crescimento
✗ 500 anotações ASTE com Codebook V3 [gargalo atual]
✗ Fine-tuning BERTimbau no corpus de cosméticos PT-BR
✗ Validação: ATE-F1 ≥ 0.70, ASTE-F1 ≥ 0.60, Kappa ≥ 0.75
✗ BERTopic integrado (topic modeling)
```

**Marco de conclusão:** BERTimbau fine-tuned com ASTE-F1 ≥ 0.60 no corpus de validação.

---

## Estágio 2 — Agente 4 operacional [após Estágio 1]

**Objetivo:** Encapsular o motor do TCC como Agente 4, integrar com a Memória Viva e produzir output padronizado para briefings.

```
Motor e dados
  ✗ Importar dinamica_absa como dependência Python do Agente 4
  ✗ Router por interaction_type (filtrar comentários relevantes)
  ✗ Classificador de briefing_relevance_score por categoria

Indicadores e output
  ✗ Calculador PN/AP/Controvérsia/Crescimento por (categoria, segmento)
  ✗ Red flags automáticos (PN alta + aspecto presente no briefing)
  ✗ Formatador de output (seção "INTELIGÊNCIA DE CONSUMIDOR")
  ✗ Síntese com Claude Haiku (contexto + linguagem do PM)

Memória
  ✗ post_batch_flush: persistir padrões no Warm Store (Agente 8)
  ✗ Busca por (categoria, segmento) na fase online
  ✗ Acúmulo de padrões entre briefings

CLI do Agente 4
  ✗ agente4 batch --input <pasta_json>    # processa corpus offline
  ✗ agente4 query "máscara de hidratação" # consulta por categoria
  ✗ agente4 status                        # corpus atual, cobertura
```

**Marco de conclusão:** Agente 4 processa um briefing de teste e entrega seção "INTELIGÊNCIA DE CONSUMIDOR" em < 10 segundos (via Warm Store).

---

## Estágio 3 — Integração LangGraph [após Agente 8 conectado ao LangGraph]

**Objetivo:** Tornar o Agente 4 um nó do grafo multi-agente, integrado ao fluxo de briefing.

```
✗ Nó LangGraph do Agente 4
✗ Recebe estado do briefing (produto, categoria, segmento alvo)
✗ Injeta "consumer_intelligence" no BriefingState
✗ Output flui para Agente 5 (RICE) e Agente 6 (Briefing Writer)
✗ Red flags bloqueantes: se PN > threshold, alerta antes do Agente 6
✗ Feedback loop: Committee Flush do Agente 8 retroalimenta o Agente 4
```

**Marco de conclusão:** Briefing completo gerado com seção de Consumer Intelligence integrada automaticamente, sem intervenção manual do PM.

---

## Estágio 4 — Expansão de cobertura [roadmap: 6+ meses]

**Objetivo:** Ampliar cobertura de categorias, segmentos e fontes.

```
Novas fontes de dados
  ✗ YouTube: comentários de reviews longos (mais argumentativos)
  ✗ Beleza na Web: reviews com estrelas + texto (contexto de compra)
  ✗ Corpus multilíngue: PT-BR + ES (mercado hispânico)

Novas categorias de produto
  ✗ Séruns e finalizadores (hoje: apenas máscaras e reposição de massa)
  ✗ Coloração (segmento tintura)
  ✗ Shampoos low poo / no poo

Modelo
  ✗ Continuous learning: atualização mensal automática com novos comentários
  ✗ Active learning: identifica comentários incertos → fila de anotação humana
  ✗ Detecção automática de novos aspectos emergentes (sem dicionário)
```

---

## Dependências críticas

```
┌─────────────────────────────────────────────────────┐
│ O Estágio 2 não começa sem o Estágio 1 concluído.   │
│                                                      │
│ O gargalo é a anotação: 500 triplas ASTE anotadas   │
│ com o Codebook V3 é o único caminho para fazer o    │
│ fine-tuning do BERTimbau funcionar.                 │
│                                                      │
│ Sem o BERTimbau fine-tuned:                         │
│  → Usar Claude Haiku como fallback (extração zero-  │
│    shot, sem offsets de span, custo por API)        │
│  → Qualidade inferior, mas funcional para protótipo │
└─────────────────────────────────────────────────────┘
```

| Dependência | Bloqueia | Estado |
|---|---|---|
| 500 anotações ASTE (TCC) | BERTimbau fine-tuning | Pendente |
| BERTimbau fine-tuned | Extração ASTE de qualidade | Pendente |
| Agente 8 conectado ao LangGraph | Estágio 3 | Pendente |
| Corpus coletado (4.802 comentários) | Estágios 1 e 2 | ✓ Disponível |
| Codebook V3 | Anotação | ✓ Disponível |
