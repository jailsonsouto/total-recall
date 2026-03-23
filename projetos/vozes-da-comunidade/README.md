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

## A convergência TCC → Vozes da Comunidade

Este projeto não começa do zero. Ele é a aplicação operacional de um trabalho acadêmico em andamento:

**TCC** — *"Da Netnografia ao ABSA/ASTE: escuta 360° da consumidora no TikTok em marcas de cosméticos"*
MBA em Data Science & Analytics, USP/ESALQ — Jailson de Castro de Souto

O TCC constrói o motor analítico: coleta, anotação, fine-tuning do BERTimbau, framework ASTE. O Vozes da Comunidade usa esse motor para gerar inteligência de produto em tempo real. **O TCC não é um projeto paralelo — é a Fase 1 do Vozes da Comunidade.**

```
TCC (Fase 1)                    Vozes da Comunidade (Fase 2)
─────────────────────────────── ──────────────────────────────
Coleta TikTok (4.802+ comments) Usa o corpus coletado
Codebook V3 de anotação         Define taxonomia de aspectos
500 anotações humanas           Dataset de fine-tuning
BERTimbau fine-tuned            Motor de extração ASTE
Indicadores PN/AP               Métricas para o briefing
```

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
| Corpus base | 4.802 comentários TikTok (JSON) | Coleta TCC |
| Motor ASTE | BERTimbau fine-tuned (neuralmind/bert-base-portuguese-cased) | TCC Fase 1 |
| Pré-processamento | TikTokTextProcessor (gírias PT-BR + emojis + ironia) | `dinamica_absa` |
| Topic modeling | BERTopic | TCC |
| Segmentação HNR | native_terms + cultural_markers do schema V1 | Codebook V3 |
| Indicadores | PN, AP, Controvérsia, Crescimento | TCC |
| Persistência | Memória Viva (Agente 8) — SQLite + sqlite-vec | Agente 8 |
| Orquestração | LangGraph | Sistema multi-agente |

---

## Documentação técnica

| Documento | Conteúdo |
|---|---|
| [docs/PRD.md](docs/PRD.md) | Problema, objetivos e métricas de sucesso |
| [docs/ARQUITETURA.md](docs/ARQUITETURA.md) | Pipeline completo, schema JSON, integração |
| [docs/ADRs.md](docs/ADRs.md) | 5 decisões de arquitetura com motivos e trade-offs |
| [ROADMAP.md](ROADMAP.md) | Fases alinhadas com o TCC |

---

## Estágio atual

```
Fase 1 — Motor ASTE (TCC)      [em andamento]
  ✓ Corpus coletado: 4.802 comentários TikTok
  ✓ Schema JSON V1 normalizado
  ✓ Codebook V3 para anotação humana
  ✓ Framework DINAMICA-ABSA estruturado (BERTimbau)
  ✓ TikTokTextProcessor (pré-processamento)
  ✗ 500 anotações ASTE completas (pendente)
  ✗ BERTimbau fine-tuned (depende das anotações)

Fase 2 — Vozes da Comunidade operacional  [roadmap: após Fase 1]
  ✗ Encapsular dinamica_absa como motor do agente
  ✗ Router por interaction_type
  ✗ Indicadores PN/AP para formato de briefing
  ✗ Integração com Memória Viva (Agente 8)

Fase 3 — Integração LangGraph  [roadmap: após Agente 8 conectado]
  ✗ Vozes da Comunidade como nó do grafo multi-agente
  ✗ Output injetado no contexto do Agente 6 (Briefing Writer)
```

---

*Parte do sistema multi-agente de briefing de produto Novex/Embelleze.*
*Motor analítico: TCC MBA DSA USP/ESALQ — Jailson de Castro de Souto.*
*Integração ao sistema: Março/2026 com Claude Code.*
