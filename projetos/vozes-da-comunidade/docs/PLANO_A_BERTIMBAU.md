# Plano A — BERTimbau Fine-tuned para ASTE

**Motor:** `neuralmind/bert-base-portuguese-cased`
**Tarefa:** Aspect-Sentiment-Triple Extraction (ASTE) via BIO tagging
**Estratégia:** Fine-tuning incremental com anotações do Codebook V3

---

## Por que é o Plano principal

O BERTimbau fine-tuned não é só um extrator — é um **ativo estratégico da Embelleze**. Cada rodada de anotações incorpora nos pesos do modelo o que é `murumuru` para cacheadas, o que distingue `reposição de massa` de `reconstrução`, o que a comunidade henêgata entende por `proteína em excesso`. Um SLM genérico nunca aprende isso — o BERTimbau acumula progressivamente.

Referências canônicas:
- Modelo base: https://huggingface.co/neuralmind/bert-base-portuguese-cased
- GitHub neuralmind: https://github.com/neuralmind-ai/portuguese-bert
- Token classification HF: https://huggingface.co/docs/transformers/tasks/token_classification
- Trainer API: https://huggingface.co/docs/transformers/training

---

## Modelo base

| Propriedade | Valor |
|---|---|
| ID HuggingFace | `neuralmind/bert-base-portuguese-cased` |
| Alternativa large | `neuralmind/bert-large-portuguese-cased` (335M, 24L — mais lento) |
| Arquitetura | BERT-base (12 camadas, 768 dim, 12 heads) |
| Tokenizador | `BertTokenizerFast` (WordPiece, vocab PT-BR) |
| Parâmetros | 110M |
| Treinamento | BrWaC + Wikipedia PT-BR (2,7B palavras) |
| Hardware | M1 MPS ou CUDA — sem diferença de código |

**Por que cased:**
Comentários de TikTok têm capitalização significativa: `AMEI`, `HORRÍVEL`, `kkkk`. O modelo cased preserva essa informação. Não existe versão uncased do BERTimbau — apenas cased (base e large).

> **Atenção:** não existe `neuralmind/bert-base-portuguese-uncased`. Qualquer referência a uncased em código antigo está errada.

---

## Pipeline de extração (DINAMICA-ABSA)

O pipeline já existe no TCC — não reimplementar. O BERTimbauExtractor encapsula sem duplicar:

```
Texto pré-processado (text_for_model)
  │
  ▼
BERTimbauEncoder
  neuralmind/bert-base-portuguese-cased
  → embeddings contextuais por token (768 dim)
  → output: last_hidden_state [batch, seq_len, 768]
  │
  ├──▶ OpenAspectExtractor
  │      Linear(768 → 3) → [O, B-ASPECT, I-ASPECT]
  │      CRF layer (decodifica sequência válida)
  │      → AspectPrediction: text, start, end, confidence
  │
  ├──▶ OpenOpinionExtractor
  │      Linear(768 → 3) → [O, B-OPINION, I-OPINION]
  │      CRF layer
  │      → OpinionPrediction: text, start, end, confidence
  │
  ▼
LearnedPairMatcher
  Biaffine attention entre spans de aspecto e opinião
  → AspectOpinionPair: aspect_text, opinion_text, confidence
  │
  ▼
ContextualPolarityClassifier
  Embedding par (aspecto, opinião) → Linear → [POS, NEG, NEU, MIX]
  → PolarityPrediction: label, confidence, scores
  │
  ▼
ExtractionResult
  → triplets: list[dict] com aspect, opinion, polarity, confidence, spans
```

---

## Dataset de fine-tuning

### Formato CoNLL (padrão para token classification)

O dataset de anotação do Codebook V3 precisa ser convertido para CoNLL-style antes do treino. Cada token em uma linha, sentença separada por linha em branco:

```
# comentário: "a máscara Novex não funciona para cabelo cacheado"
a           O
máscara     B-ASPECT
Novex       I-ASPECT
não         O
funciona    B-OPINION
para        I-OPINION
cabelo      I-OPINION
cacheado    I-OPINION
.           O
```

Para ASTE completo (aspecto + opinião + polaridade), o formato é estendido:

```
token  aspect_label  opinion_label  polarity
a      O             O              O
máscara B-ASPECT     O              NEG
Novex   I-ASPECT     O              NEG
não     O             O              O
funciona O           B-OPINION      NEG
para     O           I-OPINION      NEG
cabelo   O           I-OPINION      NEG
cacheado O           I-OPINION      NEG
```

### Volume mínimo para fine-tuning
- **500 comentários anotados** (meta do TCC) = ponto de partida funcional
- **ASTE-F1 esperado com 500 exemplos:** 0.45–0.55
- **ASTE-F1 esperado com 2.000 exemplos:** 0.60–0.70
- Referência: benchmarks ASTE em datasets SemEval (inglês: F1 ~0.60 com 1.000 ex.)

---

## Alinhamento de labels com subword tokenization

O WordPiece divide palavras em sub-tokens. `máscara` pode virar `['mas', '##car', '##a']`. O label deve ser atribuído apenas ao primeiro sub-token — os demais recebem `-100` (ignorado na loss):

```python
def tokenize_and_align_labels(examples, tokenizer, label2id):
    tokenized = tokenizer(
        examples["tokens"],
        truncation=True,
        is_split_into_words=True,   # tokens já separados
        max_length=128,
        padding="max_length",
    )
    labels = []
    for i, label_seq in enumerate(examples["tags"]):
        word_ids = tokenized.word_ids(batch_index=i)
        aligned = []
        prev_word = None
        for word_id in word_ids:
            if word_id is None:
                aligned.append(-100)          # [CLS], [SEP], padding
            elif word_id != prev_word:
                aligned.append(label2id[label_seq[word_id]])  # primeiro sub-token
            else:
                aligned.append(-100)          # sub-tokens subsequentes
            prev_word = word_id
        labels.append(aligned)
    tokenized["labels"] = labels
    return tokenized
```

Referência: https://huggingface.co/docs/transformers/tasks/token_classification#preprocess

---

## Gotchas críticos (não pular)

1. **`do_lower_case=False` é obrigatório.**
   ```python
   tokenizer = AutoTokenizer.from_pretrained(
       "neuralmind/bert-base-portuguese-cased",
       do_lower_case=False,   # NUNCA omitir — corrompe ã, é, ç silenciosamente
   )
   ```

2. **`is_split_into_words=True` é obrigatório** quando o input já é lista de tokens. Sem isso, `word_ids()` não consegue mapear sub-tokens → palavras e o alinhamento de labels quebra.

3. **Usar `-100`, não `0`, para posições ignoradas.** `0` é o ID do label `"O"` — usar `0` em `[CLS]`/`[SEP]` faz o modelo treinar sobre eles incorretamente.

4. **BIO constraint violations em inferência.** O modelo pode gerar `I-X` sem `B-X` precedente. Adicione pós-processamento com máquina de estados simples antes de extrair spans.

5. **`processing_class=tokenizer`** é a API v5.x do Trainer (substitui o deprecado `tokenizer=tokenizer`).

6. **seqeval calcula F1 no nível de span**, não de token. É a métrica correta para ASTE — accuracy por token é enganosa (maioria dos tokens é "O").

---

## Script de fine-tuning completo

```python
"""
fine_tune_bertimbau.py
Fine-tuning do BERTimbau para ASTE com HuggingFace Trainer API.

Uso:
    python fine_tune_bertimbau.py \
        --data_dir ./data/anotacoes_codebook_v3/ \
        --output_dir ./models/bertimbau-embelleze-v1 \
        --epochs 10

Para continuar de checkpoint existente (ciclo incremental):
    python fine_tune_bertimbau.py \
        --data_dir ./data/anotacoes_novo_lote/ \
        --output_dir ./models/bertimbau-embelleze-v2 \
        --resume_from ./models/bertimbau-embelleze-v1
"""
import argparse
from datasets import load_dataset
from transformers import (
    AutoTokenizer,
    AutoModelForTokenClassification,
    DataCollatorForTokenClassification,
    Trainer,
    TrainingArguments,
)
import evaluate
import numpy as np

# Labels BIO para aspecto e opinião
ASPECT_LABELS = ["O", "B-ASPECT", "I-ASPECT"]
OPINION_LABELS = ["O", "B-OPINION", "I-OPINION"]
# Para treino conjunto: unifica em label único por posição
ALL_LABELS = ["O", "B-ASPECT", "I-ASPECT", "B-OPINION", "I-OPINION"]

label2id = {l: i for i, l in enumerate(ALL_LABELS)}
id2label = {i: l for i, l in enumerate(ALL_LABELS)}

MODEL_NAME = "neuralmind/bert-base-portuguese-cased"
seqeval = evaluate.load("seqeval")


def compute_metrics(p):
    predictions, labels = p
    predictions = np.argmax(predictions, axis=2)
    true_preds = [
        [id2label[pred] for pred, lbl in zip(preds, lbls) if lbl != -100]
        for preds, lbls in zip(predictions, labels)
    ]
    true_labels = [
        [id2label[lbl] for lbl in lbls if lbl != -100]
        for lbls in labels
    ]
    results = seqeval.compute(predictions=true_preds, references=true_labels)
    return {
        "precision": results["overall_precision"],
        "recall": results["overall_recall"],
        "f1": results["overall_f1"],           # métrica principal
        "accuracy": results["overall_accuracy"],
    }


def main(args):
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    dataset = load_dataset("conll2003", data_dir=args.data_dir)  # adaptar ao formato real

    # Tokenizar e alinhar labels
    tokenized = dataset.map(
        lambda ex: tokenize_and_align_labels(ex, tokenizer, label2id),
        batched=True,
    )

    model_init = args.resume_from or MODEL_NAME
    model = AutoModelForTokenClassification.from_pretrained(
        model_init,
        num_labels=len(ALL_LABELS),
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=bool(args.resume_from),
    )

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        learning_rate=2e-5,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        num_train_epochs=args.epochs,
        weight_decay=0.01,
        warmup_ratio=0.1,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        # Apple Silicon M1
        use_mps_device=True,   # ou: use_cpu=True se MPS tiver problemas
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized["validation"],
        processing_class=tokenizer,   # API v5.x — substitui tokenizer= (deprecado)
        data_collator=DataCollatorForTokenClassification(tokenizer),
        compute_metrics=compute_metrics,
    )

    trainer.train()
    trainer.save_model(args.output_dir)
    print(f"Modelo salvo em: {args.output_dir}")
    print(f"Melhor F1: {trainer.state.best_metric:.4f}")
```

---

## Métricas de avaliação

O `seqeval` calcula F1 no nível de span (não token) — alinhado com o ASTE-F1:

| Métrica | Descrição | Threshold mínimo |
|---|---|---|
| Aspecto F1 | F1 de identificação de spans de aspecto | 0.55 |
| Opinião F1 | F1 de identificação de spans de opinião | 0.55 |
| ASTE-F1 | F1 da tripla completa (aspecto + opinião + polaridade) | 0.45 (500 ex.) / 0.60 (2k ex.) |
| Accuracy | Acurácia por token | — (informativo) |

Referência seqeval: https://github.com/chakki-works/seqeval

---

## Ciclo incremental de fine-tuning

```
Ciclo N (primeiro):
  ├── Data: 500 comentários anotados (TCC)
  ├── Base: neuralmind/bert-base-portuguese-cased
  ├── Output: ./models/bertimbau-embelleze-v1/
  └── ASTE-F1 esperado: 0.45–0.55

Ciclo N+1 (incremental):
  ├── Data: 500 novos comentários anotados + dataset anterior
  ├── Base: ./models/bertimbau-embelleze-v1/  (--resume_from)
  ├── Output: ./models/bertimbau-embelleze-v2/
  └── ASTE-F1 esperado: 0.55–0.65

Ciclo N+k (maduro):
  ├── Data: corpus acumulado (2.000+ comentários)
  ├── Base: último checkpoint
  └── ASTE-F1 esperado: 0.65–0.75
```

**Regra de promoção:** só atualiza `BERTIMBAU_MODEL_PATH` no `.env` se o novo ASTE-F1 ≥ F1 anterior − 0.02 (tolerância para flutuação de validação).

---

## Requisitos de hardware

| Operação | Hardware | Tempo estimado |
|---|---|---|
| Fine-tuning (500 ex., 10 épocas) | M1 MPS | ~30–45 min |
| Fine-tuning (2.000 ex., 10 épocas) | M1 MPS | ~2–3h |
| Inferência batch (4.802 comentários) | M1 MPS | ~2–4h |
| Inferência por comentário | M1 MPS | ~50ms |

Para ativar MPS no M1:
```python
import torch
device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
model = model.to(device)
```
