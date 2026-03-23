# Vozes da Comunidade

> *"A consumidora já disse tudo que o PM precisa saber. Ela disse no TikTok, às 23h, depois de usar o produto por duas semanas. O problema é que ninguém estava ouvindo de forma sistemática."*

O Vozes da Comunidade é a camada de escuta do sistema multi-agente. Enquanto o Agente 1 avalia o alinhamento com o Código Genético da marca e o Agente 2 prevê o BVS, o Vozes da Comunidade responde a uma pergunta diferente: **o que a consumidora real — cacheada, enrolada, henêgata — já pensa sobre produtos desta categoria?**

---

## O que ele faz

Antes de um briefing ser finalizado, o Vozes da Comunidade consulta o corpus de comentários de TikTok coletados sobre a categoria do produto. A partir de um corpus de 4.800+ comentários reais e crescendo, ele extrai:

- **Triplas ASTE** por comentário: `(aspecto, expressão de opinião, polaridade)` — não apenas "sentimento positivo", mas *por que* a consumidora sente aquilo
- **Segmentação HNR** automática: identifica se a voz é de uma consumidora cacheada, enrolada ou henêgata, e pondera o insight de acordo
- **Indicadores acionáveis** para o briefing: PN (Prioridade Negativa), AP (Alavancagem Positiva), Controvérsia, Crescimento
- **Red flags**: ingredientes, claims ou formatos que a comunidade rejeita — antes que o briefing chegue ao Comitê

---

## Ativos cedidos pelo TCC

Este projeto parte de um conjunto de ativos desenvolvidos de forma independente no contexto do TCC *"Da Netnografia ao ABSA/ASTE: escuta 360° da consumidora no TikTok em marcas de cosméticos"* (MBA DSA, USP/ESALQ). São projetos distintos — o TCC tem objetivos acadêmicos próprios; o Vozes da Comunidade tem objetivos operacionais. O que foi cedido:

| Ativo | Descrição |
|---|---|
| Corpus TikTok | 4.802 comentários reais (JSON, schema V1 normalizado) |
| TikTokTextProcessor | Pré-processamento: gírias PT-BR, emojis, ironia |
| Framework DINAMICA-ABSA | Arquitetura BERTimbau (4 camadas) — estruturada, aguarda fine-tuning |
| Codebook V3 | Taxonomia de aspectos + regras de anotação ASTE |
| Indicadores | PN, AP, Controvérsia, Crescimento — definidos e validados |

---

## O que o Vozes da Comunidade entrega ao briefing

### Exemplo de output — categoria: Máscaras de Reconstrução

```
## INTELIGÊNCIA DE CONSUMIDOR

### Segmento dominante: Cacheadas (73% do corpus nesta categoria)

Dores principais (PN alta):
1. (silicone, "acumula e mata o cacho", NEG) — 47 menções, crescendo +18%
2. (proteína excessiva, "endurece o fio", NEG) — 31 menções
3. (fragrância, "cheiro muito forte, fica no cabelo", NEG) — 19 menções

Atributos que convertem (AP alta):
1. (murumuru, "hidratação sem pesar", POS) — 28 menções ⚑ relevante para esta formulação
2. (low poo compatível, "dá pra usar sem sulfato", POS) — 44 menções
3. (desembaraço, "penteia com os dedos molhado", POS) — 38 menções

Red flags — rejeição automática neste segmento:
⛔ Silicones pesados (D4/D5) → risco de post viral negativo
⛔ Claim "liso" ou "alinhado" → conflito de identidade com cacheadas
⛔ Tempo de ação > 20 min → incompatível com rotina do segmento

⚠️  Controvérsia detectada: "reposição de massa ≠ reconstrução"
   Tema divisório na comunidade. Usar terminologia com precisão no copy.

Score de oportunidade neste segmento: 7.8/10
```

---

## Stack

| Componente | Tecnologia | Origem |
|---|---|---|
| Corpus base | 4.802 comentários TikTok (JSON) | Cedido pelo TCC |
| Motor ASTE | BERTimbau fine-tuned (neuralmind/bert-base-portuguese-cased) | Cedido pelo TCC |
| Pré-processamento | TikTokTextProcessor (gírias PT-BR + emojis + ironia) | Cedido pelo TCC |
| Topic modeling | BERTopic | Cedido pelo TCC |
| Segmentação HNR | native_terms + cultural_markers do schema V1 | Cedido pelo TCC |
| Indicadores | PN, AP, Controvérsia, Crescimento | Cedido pelo TCC |
| Persistência | Memória Viva (Agente 8) — SQLite + sqlite-vec | Agente 8 |
| Orquestração | LangGraph | Sistema multi-agente |

---

## Documentação técnica

| Documento | Conteúdo |
|---|---|
| [docs/PRD.md](docs/PRD.md) | Problema, objetivos e métricas de sucesso |
| [docs/ARQUITETURA.md](docs/ARQUITETURA.md) | Pipeline completo, schema JSON, integração |
| [docs/ADRs.md](docs/ADRs.md) | 5 decisões de arquitetura com motivos e trade-offs |
| [ROADMAP.md](ROADMAP.md) | Estágios de implementação |

---

## Estágio atual

```
Ativos recebidos do TCC (ponto de partida)
  ✓ Corpus: 4.802 comentários TikTok (JSON, schema V1)
  ✓ TikTokTextProcessor (pré-processamento)
  ✓ Framework DINAMICA-ABSA estruturado (BERTimbau, 4 camadas)
  ✓ Codebook V3 de anotação
  ✓ Indicadores PN/AP/Controvérsia/Crescimento definidos

Estágio 1 — MVP operacional    [próximo]
  ✗ Encapsular dinamica_absa como motor do agente
  ✗ Router por interaction_type
  ✗ Calculador de indicadores por (categoria, segmento)
  ✗ Síntese com Claude Haiku (extração ASTE zero-shot)
  ✗ Integração com Memória Viva (Agente 8)

Estágio 2 — Upgrade de qualidade    [paralelo ao TCC]
  ✗ BERTimbau fine-tuned (plug-in quando o TCC entregar)
  ✗ Re-processar corpus com modelo de maior precisão

Estágio 3 — Integração LangGraph  [após Agente 8 conectado]
  ✗ Vozes da Comunidade como nó do grafo multi-agente
  ✗ Output injetado no contexto do Agente 6 (Briefing Writer)
```

---

*Parte do sistema multi-agente de briefing de produto Novex/Embelleze.*
*Ativos cedidos pelo TCC MBA DSA USP/ESALQ — Jailson de Castro de Souto.*
*Integração ao sistema: Março/2026 com Claude Code.*
