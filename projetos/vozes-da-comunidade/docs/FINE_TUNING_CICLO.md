# Ciclo Incremental de Fine-tuning

**Aplicável a:** Plano A (BERTimbau) e Plano B (SLM com LoRA)
**Princípio:** cada nova rodada de anotações melhora o modelo sem reescrever código

---

## O ciclo

```
┌─────────────────────────────────────────────────────────────────┐
│  1. COLETA                                                       │
│     Novos comentários chegam via corpus TikTok                   │
│     (coleta manual com Chrome extension — ADR-003)               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. TRIAGEM (Router)                                             │
│     Filtra por interaction_type:                                 │
│     ✓ product_opinion | comparison | technical_question          │
│     ✗ social_or_phatic | creator_reply | short_or_emoji_only     │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. ANOTAÇÃO HUMANA                                              │
│     Codebook V3 — dupla codificação                              │
│     Anotador 1 + Anotador 2 → resolução de divergências          │
│     Meta: 50–100 comentários por rodada                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. CONVERSÃO DO DATASET                                         │
│     Anotações Codebook V3 → formato de treino                    │
│     Plano A: CoNLL (token + BIO labels)                          │
│     Plano B: JSONL chat (instruction-following)                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. FINE-TUNING                                                  │
│     Plano A: Trainer API com --resume_from_checkpoint            │
│     Plano B: mlx_lm.lora com dataset acumulado                   │
│     Treinamento em cima do checkpoint anterior                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  6. AVALIAÇÃO                                                    │
│     Medir ASTE-F1 no conjunto de validação                       │
│     Comparar com F1 do checkpoint anterior                       │
│     Promoção: F1_novo ≥ F1_anterior − 0.02                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │ F1 melhorou?                 │
              │                             │
              ▼ Sim                         ▼ Não
┌─────────────────────────┐   ┌─────────────────────────────┐
│  7a. PROMOÇÃO           │   │  7b. INVESTIGAÇÃO            │
│  Atualizar .env:        │   │  Verificar qualidade das     │
│  BERTIMBAU_MODEL_PATH   │   │  novas anotações             │
│  ou SLM_MODEL           │   │  Manter checkpoint anterior  │
└─────────────────────────┘   └─────────────────────────────┘
```

---

## Conversão de anotações Codebook V3 → dataset de treino

### Para o Plano A (CoNLL)

O schema V1 já inclui `manual_coding.aste_triplets` após anotação:

```json
{
  "manual_coding": {
    "aste_triplets": [
      {
        "aspect_text": "máscara Novex",
        "aspect_start": 2,
        "aspect_end": 13,
        "opinion_text": "não funciona para cabelo cacheado",
        "opinion_start": 14,
        "opinion_end": 46,
        "polarity": "NEGATIVE"
      }
    ]
  }
}
```

Script de conversão (esboço — adaptar ao schema real):

```python
def json_v1_to_conll(comment: dict) -> str:
    """Converte um comentário anotado em formato CoNLL."""
    tokens = comment["text_for_model"].split()
    labels = ["O"] * len(tokens)

    for triplet in comment.get("manual_coding", {}).get("aste_triplets", []):
        # Marcar tokens de aspecto
        asp_tokens = triplet["aspect_text"].split()
        for i, tok in enumerate(tokens):
            if tok in asp_tokens:
                labels[i] = "B-ASPECT" if i == 0 else "I-ASPECT"

        # Marcar tokens de opinião
        opn_tokens = triplet["opinion_text"].split()
        for i, tok in enumerate(tokens):
            if tok in opn_tokens and labels[i] == "O":
                labels[i] = "B-OPINION" if i == 0 else "I-OPINION"

    lines = [f"{tok}\t{lbl}" for tok, lbl in zip(tokens, labels)]
    return "\n".join(lines) + "\n\n"
```

### Para o Plano B (JSONL chat)

```python
def json_v1_to_jsonl_chat(comment: dict) -> dict:
    """Converte um comentário anotado em exemplo de instrução para LoRA."""
    text = comment["text_for_model"]
    triplets = comment.get("manual_coding", {}).get("aste_triplets", [])

    answer = {
        "triplas": [
            {
                "aspecto": t["aspect_text"],
                "opiniao": t["opinion_text"],
                "polaridade": t["polarity"][:3].upper(),  # POSITIVE → POS
                "confianca": 0.95,  # anotação humana = alta confiança
                "categoria_aspecto": t.get("aspect_category", "PRODUTO"),
            }
            for t in triplets
        ]
    }

    return {
        "messages": [
            {"role": "user", "content": f'Extraia ASTE do comentário: "{text}"'},
            {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)},
        ]
    }
```

---

## Versionamento de modelos

Convenção de nomes para checkpoints:

```
models/
├── bertimbau-embelleze-v1/     # 500 exemplos, ciclo 1 (TCC)
│   ├── config.json
│   ├── pytorch_model.bin
│   └── training_log.json       # F1=0.48, data=2026-04-01, n_examples=500
├── bertimbau-embelleze-v2/     # 1.000 exemplos, ciclo 2
│   └── training_log.json       # F1=0.57, data=2026-06-01, n_examples=1000
└── qwen-aste-adapters-v1/      # LoRA adapters do Plano B
    └── training_log.json
```

`training_log.json` — campos obrigatórios:
```json
{
  "versao": "v2",
  "data_treino": "2026-06-01",
  "n_exemplos_treino": 1000,
  "n_exemplos_validacao": 125,
  "base_checkpoint": "bertimbau-embelleze-v1",
  "aste_f1": 0.57,
  "aspecto_f1": 0.63,
  "opiniao_f1": 0.61,
  "epocas": 10,
  "hardware": "M1 MPS"
}
```

---

## Critérios de qualidade das anotações (antes de incluir no dataset)

1. **Cohen's Kappa ≥ 0.70** entre os dois anotadores no lote — abaixo disso, rever instruções do Codebook V3
2. **Pelo menos 3 triplas por 10 comentários** — lotes muito esparsos não contribuem para o treino
3. **Distribuição de polaridade balanceada** — evitar datasets com >70% NEG ou >70% POS
4. **Cobertura de categorias**: garantir que o novo lote inclua exemplos de pelo menos 5 categorias do Codebook V3 diferentes

---

## Frequência recomendada

| Estágio | Volume por rodada | Frequência |
|---|---|---|
| Arranque (TCC) | 500 comentários | Uma vez (baseline) |
| Crescimento | 100–200 por rodada | Mensal |
| Maturidade | 50–100 por rodada | Trimestral |

O modelo entra em maturidade quando ASTE-F1 ≥ 0.65 e parar de melhorar significativamente entre rodadas (< 0.02 de ganho). Nesse ponto, rodadas menores de anotação focadas em categorias sub-representadas são mais eficientes que volume bruto.
