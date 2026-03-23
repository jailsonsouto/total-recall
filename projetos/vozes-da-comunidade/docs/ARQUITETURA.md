# Arquitetura — Vozes da Comunidade

**Versão:** 1.0 | **Data:** Março/2026

---

## Visão geral do pipeline

O Agente 4 opera em duas fases distintas:

- **Fase offline** (roda em batch, independente do briefing): processa o corpus TikTok, extrai triplas ASTE, calcula indicadores por categoria/segmento, persiste no Warm Store da Memória Viva.
- **Fase online** (roda por briefing): o Agente 8 injeta os padrões pré-computados no contexto do Agente 4, que monta o output para o briefing.

```
╔══════════════════════════════════════════════════════════════════╗
║                    FASE OFFLINE (batch)                         ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  TikTok JSONs (schema V1)                                        ║
║       │                                                          ║
║       ▼                                                          ║
║  ┌────────────────────────────────────────────────────────────┐  ║
║  │  ROUTER                                                     │  ║
║  │  Filtra por interaction_type:                               │  ║
║  │  ✓ product_opinion, comparison, technical_question          │  ║
║  │  ✗ social_or_phatic, creator_reply, short_or_emoji_only     │  ║
║  └────────────────────┬───────────────────────────────────────┘  ║
║                       │                                          ║
║                       ▼                                          ║
║  ┌────────────────────────────────────────────────────────────┐  ║
║  │  TIKTOKTEXTPROCESSOR (dinamica_absa)                        │  ║
║  │  ▸ Normaliza gírias PT-BR ("n" → "não", "mt" → "muito")    │  ║
║  │  ▸ Mapeia emojis → sentimento (😍 POS, 🤡 ironia)          │  ║
║  │  ▸ Detecta padrões de ironia (😂+🤡, "claro que sim")      │  ║
║  │  ▸ Constrói text_for_model (inclui [PARENT] em replies)     │  ║
║  └────────────────────┬───────────────────────────────────────┘  ║
║                       │                                          ║
║                       ▼                                          ║
║  ┌────────────────────────────────────────────────────────────┐  ║
║  │  BERTIMBAU PIPELINE (dinamica_absa — 4 camadas)             │  ║
║  │                                                             │  ║
║  │  Camada 1 — Encoding                                        │  ║
║  │    BERTimbau (neuralmind/bert-base-portuguese-cased)        │  ║
║  │    → embeddings contextuais por token                       │  ║
║  │                                                             │  ║
║  │  Camada 2 — Extraction (open vocabulary)                    │  ║
║  │    Aspect Decoder  → BIO tagging (B-ASP, I-ASP, O)         │  ║
║  │    Opinion Decoder → BIO tagging (B-OPN, I-OPN, O)         │  ║
║  │    Pair Matcher    → biaffine attention (aprendido)         │  ║
║  │                                                             │  ║
║  │  Camada 3 — Classification                                  │  ║
║  │    Polarity Classifier → POS / NEG / NEU / MIX             │  ║
║  │    Confidence Estimator → score por tripla                  │  ║
║  │    → Triplet: (aspecto, opinião, polaridade, confiança)     │  ║
║  │                                                             │  ║
║  │  Camada 4 — Adaptation (contínua, por lote)                 │  ║
║  │    Few-shot update com novas anotações validadas            │  ║
║  └────────────────────┬───────────────────────────────────────┘  ║
║                       │                                          ║
║                       ▼                                          ║
║  ┌────────────────────────────────────────────────────────────┐  ║
║  │  CLASSIFICADOR DE CATEGORIA + SEGMENTO HNR                  │  ║
║  │  ▸ Categoria: similaridade semântica com embedding          │  ║
║  │    do produto do briefing                                   │  ║
║  │  ▸ Segmento HNR: via native_terms + cultural_markers        │  ║
║  │    do schema V1 (cacheadas, enroladas, henêgatas)           │  ║
║  └────────────────────┬───────────────────────────────────────┘  ║
║                       │                                          ║
║                       ▼                                          ║
║  ┌────────────────────────────────────────────────────────────┐  ║
║  │  BERTOPIC — Topic Modeling                                  │  ║
║  │  ▸ Embeddings dos comentários → clusters de tópicos         │  ║
║  │  ▸ Rótulos automáticos por categoria                        │  ║
║  │  ▸ Permite detectar tópicos emergentes não previstos        │  ║
║  └────────────────────┬───────────────────────────────────────┘  ║
║                       │                                          ║
║                       ▼                                          ║
║  ┌────────────────────────────────────────────────────────────┐  ║
║  │  CALCULADOR DE INDICADORES                                  │  ║
║  │  PN = Prioridade Negativa (frequência × intensidade neg)    │  ║
║  │  AP = Alavancagem Positiva (frequência × engajamento pos)   │  ║
║  │  Controvérsia = equilíbrio pos/neg por aspecto              │  ║
║  │  Crescimento = variação temporal de frequência              │  ║
║  └────────────────────┬───────────────────────────────────────┘  ║
║                       │                                          ║
║                       ▼                                          ║
║         Persiste no Warm Store (Agente 8)                        ║
║         → memory_patterns por (categoria, segmento)              ║
║                                                                  ║
╠══════════════════════════════════════════════════════════════════╣
║                    FASE ONLINE (por briefing)                    ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Briefing submetido → Agente 8 injeta contexto                   ║
║       │                                                          ║
║       ▼                                                          ║
║  Agente 4 recebe:                                                ║
║    ▸ categoria do produto (embedding)                            ║
║    ▸ segmento HNR alvo                                           ║
║    ▸ ingredientes chave da formulação                            ║
║       │                                                          ║
║       ▼                                                          ║
║  Busca no Warm Store:                                            ║
║    ▸ hybrid_search(categoria + segmento)                         ║
║    ▸ filtra por briefing_relevance_score > 0.6                   ║
║       │                                                          ║
║       ▼                                                          ║
║  Claude Haiku: sintetiza em seção do briefing                    ║
║    → "INTELIGÊNCIA DE CONSUMIDOR" (formato padronizado)          ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## Schema de entrada — JSON V1

O Agente 4 consome JSONs no formato definido em `MODELO_JSON_EXPLORATORIO_TCC_V1.json`. Os campos mais relevantes para o pipeline:

### Por vídeo

```json
{
  "study_context": {
    "case_company": "Embelleze",
    "subcases": ["Novex"],
    "domain": "cosmeticos_capilares"
  },
  "video": {
    "brand_primary": "Novex",
    "brand_confidence": 0.93,
    "netnography_video_memo": {
      "community_type": "consumidoras_e_especialistas",
      "macro_theme": "reposicao_de_massa_reconstrucao_claims"
    }
  }
}
```

### Por comentário — campos consumidos pelo pipeline

```json
{
  "speaker_role": "consumer",
  "interaction_type": "product_opinion",
  "text_for_model": "a máscara da novex reposição de massa não funciona para cabelo cacheado",
  "linguistic_signals": {
    "has_negation": true,
    "has_irony_signal": false,
    "has_comparison_signal": false
  },
  "netnography": {
    "interaction_type": "product_opinion",
    "consumption_stage": "post_use",
    "native_terms": ["reposição de massa", "cronograma capilar"],
    "cultural_markers": ["cacheada", "método curly"],
    "memo_tags": ["insatisfação", "eficácia"]
  },
  "eligibility": {
    "is_eligible": true
  }
}
```

### Segmentação HNR por campo `netnography`

| Segmento | `native_terms` esperados | `cultural_markers` esperados |
|---|---|---|
| Cacheadas | "método curly", "gel ativador", "cachos", "low poo" | "cacheada", "crespa", "2c", "3a", "4c" |
| Enroladas | "ondulado", "fininho", "umidade", "transição" | "enrolada", "ondulada", "1c", "2a" |
| Henêgatas | "progressiva", "alisamento", "relaxamento", "reconstrução" | "henê", "progressiva", "danificado" |

---

## Schema de saída — para o briefing

O Agente 4 entrega uma estrutura padronizada que o Agente 6 (Briefing Writer) usa diretamente:

```python
@dataclass
class ConsumerIntelligenceOutput:
    # Metadados
    categoria_produto: str
    segmento_dominante: str          # "cacheadas" | "enroladas" | "henêgatas"
    segmento_score: float            # proporção do corpus neste segmento
    total_comentarios_analisados: int
    briefing_relevance_score: float

    # Triplas ASTE agregadas
    dores_principais: list[ASTETriplet]        # PN alta, NEG
    atributos_conversao: list[ASTETriplet]     # AP alta, POS
    aspectos_controversos: list[ASTETriplet]   # Controvérsia > 0.4
    tendencias_emergentes: list[ASTETriplet]   # Crescimento > 0.3

    # Red flags para o briefing
    red_flags: list[str]             # ingredientes/claims rejeitados

    # Alertas para o Comitê
    alertas: list[str]               # textos de alerta prontos para injeção

    # Score síntese
    score_oportunidade: float        # 0-10 (AP alta - PN alta + crescimento)
```

```python
@dataclass
class ASTETriplet:
    aspecto: str                     # ex: "silicone"
    opiniao: str                     # ex: "acumula e mata o cacho"
    polaridade: str                  # "POS" | "NEG" | "NEU" | "MIX"
    frequencia: int                  # nº de comentários com este padrão
    confianca_media: float           # confiança média do modelo
    crescimento: float               # variação temporal (%)
    categoria_aspecto: str           # ex: "ATIVO_INGREDIENTE"
```

---

## Integração com o sistema multi-agente

### Com o Agente 8 (Memória Viva)

O Agente 4 persiste dois tipos de dados no Agente 8:

**1. Post-batch (fase offline):**

```python
# Após processar lote de JSONs, persiste padrões agregados
memory_manager.post_batch_flush(
    categoria="mascara_reconstrucao",
    segmento="cacheadas",
    pattern_type="consumer_intel",
    content=consumer_intel_output.to_dict(),
    embedding=embed(consumer_intel_output.summary())
)
```

**2. Post-briefing (fase online):**

O Agente 8 já cuida do Committee Flush. O Agente 4 não precisa escrever diretamente — recebe feedback via `insert_bvs_real` quando o produto é lançado e o sell-through revela se os red flags eram corretos.

### Com o Agente 6 (Briefing Writer)

O output do Agente 4 é injetado como seção estruturada:

```markdown
## INTELIGÊNCIA DE CONSUMIDOR

**Segmento dominante:** Cacheadas (73% do corpus relevante)
**Comentários analisados:** 847 | **Score de oportunidade:** 7.8/10

### Dores do segmento (PN alta)
1. (silicone, "acumula e mata o cacho", NEG) — 47 menções, +18% trim.
2. (proteína excessiva, "endurece o fio", NEG) — 31 menções
3. (fragrância, "cheiro muito forte, fica no cabelo", NEG) — 19 menções

### O que converte (AP alta)
1. (murumuru, "hidratação sem pesar", POS) — 28 menções ⚑
2. (low poo compatível, "dá pra usar sem sulfato", POS) — 44 menções
3. (desembaraço, "penteia com os dedos molhado", POS) — 38 menções

### Red flags — rejeição automática neste segmento
⛔ Silicones pesados (D4/D5) → risco de post viral negativo
⛔ Claim "liso" ou "alinhado" → conflito de identidade
⛔ Tempo de ação > 20 min → incompatível com rotina do segmento

### ⚠️ Alerta de controvérsia
"reposição de massa ≠ reconstrução" — tema divisório no corpus.
Usar terminologia com precisão no copy. Risco de engajamento negativo
se o claim usar os termos de forma intercambiável.
```

### Com o LangGraph (orquestrador)

O Agente 4 é um nó do grafo que roda após o Agente 3 (Análise Competitiva) e antes do Agente 5 (Priorização RICE):

```python
# Pseudo-código do nó no grafo LangGraph
def agente4_node(state: BriefingState) -> BriefingState:
    produto = state["produto"]
    categoria = state["categoria"]

    # Busca no Warm Store (Agente 8 já injetou contexto)
    context = state["memory_context"]
    consumer_patterns = context.get_consumer_patterns(categoria)

    # Se há padrões persistidos — usa direto (fase online rápida)
    if consumer_patterns:
        output = sintetizar_com_haiku(consumer_patterns, produto)
    else:
        # Fallback: roda análise ad-hoc no corpus (mais lento)
        output = rodar_pipeline_completo(corpus, produto)

    state["consumer_intelligence"] = output
    return state
```

---

## Localização do código-fonte

O motor do Agente 4 reside no projeto TCC, não neste repositório. A integração é por importação:

```
COLETA-COMENTARIOS-TIKTOK/PROCESSAMENTO-COLETA/kimi/
├── package/
│   ├── dinamica_absa/          ← motor ASTE (BERTimbau)
│   │   └── src/models/         ← aspect_extractor, opinion_extractor, pair_matcher
│   └── absa_tiktok_processor/  ← processador atual (BOW, limitado)
└── dinamica_absa/              ← versão mais madura (codebook V3)
    └── docs/
        └── MODELO_JSON_EXPLORATORIO_TCC_V1.json  ← schema canônico
```

Quando o BERTimbau for fine-tuned, o Agente 4 importa `dinamica_absa` como pacote Python e encapsula a interface de extração.

---

## Considerações de desempenho

| Operação | Frequência | Tempo estimado |
|---|---|---|
| Batch offline (4.802 comentários) | Mensal | ~2-4h (M1, CPU) |
| Busca no Warm Store por briefing | Por briefing | < 200ms |
| Síntese com Claude Haiku | Por briefing | < 5s |
| Fine-tuning BERTimbau (500 exemplos) | Uma vez + updates | ~30min (M1 MPS) |

O custo computacional pesado (batch) roda offline, não no caminho crítico do briefing.
