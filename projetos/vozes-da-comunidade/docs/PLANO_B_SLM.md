# Plano B — SLM Local para ASTE

**Motor:** Qwen2.5-7B-Instruct (ou equivalente)
**Backend:** ollama (simples) ou MLX-LM (nativo Apple Silicon)
**Estratégia:** Zero-shot via prompt estruturado + LoRA fine-tuning opcional

---

## Papel do Plano B

O SLM é o motor de arranque — funciona imediatamente sem fine-tuning. Não acumula conhecimento da Embelleze nos pesos (a menos que se faça LoRA), mas entrega extração ASTE funcional em PT-BR informal desde o primeiro dia.

Situações de uso:
1. **MVP**: antes do BERTimbau ter anotações suficientes para fine-tuning
2. **Fallback automático**: quando `BERTIMBAU_MODEL_PATH` não está configurado
3. **Casos ambíguos**: comentários longos ou irônicos onde o raciocínio do SLM supera o BIO tagging

Referências canônicas:
- Qwen2.5 HuggingFace: https://huggingface.co/Qwen/Qwen2.5-7B-Instruct
- ollama GitHub: https://github.com/ollama/ollama
- MLX-LM GitHub: https://github.com/ml-explore/mlx-lm
- MLX LoRA: https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md

---

## Modelos recomendados (M1 16GB)

| Modelo | Tamanho | Backend | Uso recomendado |
|---|---|---|---|
| `qwen2.5:7b` | ~4.5 GB RAM | ollama | Primeiro uso — setup mais simples |
| `mlx-community/Qwen2.5-7B-Instruct-4bit` | 4.28 GB | MLX-LM | Batch offline — mais rápido no M1 |
| `mlx-community/Qwen2.5-7B-Instruct-8bit` | 8.09 GB | MLX-LM | Maior qualidade (tight em 16 GB) |
| `phi3.5` | ~2.2 GB | ollama | Latência mínima, qualidade menor |

**Por que Qwen2.5 para PT-BR informal:**
O Qwen2.5-7B foi treinado em 18 trilhões de tokens cobrindo 29 idiomas. Entre os modelos open-source no range 3B–7B, apresenta melhor desempenho em PT-BR informal baseado em benchmarks multilíngues disponíveis no HuggingFace Open LLM Leaderboard (março/2026).

---

## Setup — Backend ollama

### Instalação

```bash
# 1. Instalar ollama (macOS)
# Download: https://ollama.com/download
# Ou via brew:
brew install ollama

# 2. Iniciar servidor
ollama serve

# 3. Baixar modelo (uma vez, ~4.5 GB)
ollama pull qwen2.5:7b

# 4. Instalar cliente Python
pip install ollama
```

### Uso básico

```python
import ollama

from pydantic import BaseModel
from typing import Literal

class TripletSchema(BaseModel):
    aspecto: str
    opiniao: str
    polaridade: Literal["POS", "NEG", "NEU", "MIX"]
    confianca: float
    categoria_aspecto: str

class ASTESchema(BaseModel):
    triplas: list[TripletSchema]

response = ollama.chat(
    model="qwen2.5:7b",
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": USER_PROMPT},
    ],
    format=ASTESchema.model_json_schema(),  # constrained decoding por schema
    options={"temperature": 0},             # temperatura 0 = determinístico
)

result = ASTESchema.model_validate_json(response["message"]["content"])
# result.triplas[0].polaridade será sempre "POS"|"NEG"|"NEU"|"MIX"
```

**`format=schema_dict`** (não apenas `format="json"`) ativa constrained decoding por schema no ollama. Garante não só JSON válido, mas também tipos corretos e enums válidos — `polaridade` nunca sairá como `"POSITIVE"` ou `"negativo"`. Mais robusto que `format="json"` puro. Referência: https://github.com/ollama/ollama/blob/main/docs/api.md#request-json-mode

---

## Setup — Backend MLX-LM (Apple Silicon nativo)

### Instalação

```bash
# Requer Apple Silicon (M1/M2/M3)
pip install mlx-lm
```

### Download e uso

```python
from mlx_lm import load, generate

# Modelo 4-bit quantizado: 4.28 GB → cabe em M1 16GB
model, tokenizer = load("mlx-community/Qwen2.5-7B-Instruct-4bit")

messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user",   "content": USER_PROMPT},
]

# Aplicar chat template
prompt = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
)

response = generate(
    model,
    tokenizer,
    prompt=prompt,
    max_tokens=512,
    verbose=False,
)
```

### MLX vs ollama — quando usar cada um

| Critério | ollama | MLX-LM |
|---|---|---|
| Setup | mais simples | requer Apple Silicon |
| Velocidade batch | moderada | ~20–30% mais rápido (GPU unificada M1) |
| Modelos disponíveis | qualquer modelo suportado | apenas modelos convertidos para MLX |
| JSON garantido | sim (`format="json"`) | não nativo — necessário parsear |
| LoRA fine-tuning | não | sim (`mlx_lm.lora`) |

**Recomendação:** comece com ollama. Migre para MLX quando precisar de velocidade em batch ou quiser fazer LoRA fine-tuning.

---

## Prompt template completo

```
SYSTEM:
Você é um especialista em análise de sentimentos (ABSA/ASTE) para cosméticos capilares.
Seu foco é PT-BR informal: gírias, emojis, ironia, linguagem de TikTok.

Categorias de aspecto válidas (Codebook V3):
PRODUTO | RESULTADO_EFICACIA | TEXTURA_CABELO | TEXTURA_PRODUTO |
EMBALAGEM | APLICACAO | CUSTO | CRONOGRAMA_CAPILAR | PRESCRITOR |
CABELO_TIPO | ATIVO_INGREDIENTE | CLAIM_EFICACIA |
CUSTO_PERCEBIDO | ROTINA_CRONOGRAMA

Regras obrigatórias:
1. Aspecto = expressão exata do texto
2. Opinião = expressão exata do texto
3. Polaridade: POS | NEG | NEU | MIX
4. Ironia (🤡, "claro que...", kkk após reclamação): polaridade inversa ao aparente
5. Gírias: interprete o significado real ("n salvou" = não salvou = NEG)
6. Um comentário pode ter ZERO ou VÁRIAS triplas
7. Responda SOMENTE JSON

USER:
Contexto do vídeo: {macro_theme}
Segmento inferido: {segmento_hnr}
Marca primária: {marca_primaria}
Ironia sinalizada: {has_irony}
Negação presente: {has_negation}

Comentário:
"{text}"

Responda:
{
  "triplas": [
    {
      "aspecto": "<expressão exata do texto>",
      "opiniao": "<expressão exata do texto>",
      "polaridade": "POS|NEG|NEU|MIX",
      "confianca": 0.0,
      "categoria_aspecto": "<categoria do Codebook V3>"
    }
  ]
}
```

### Exemplos de extração correta

**Entrada:** `"amei a máscara da novex, deixa o cabelo macio sem pesar"`
**Saída esperada:**
```json
{
  "triplas": [
    {
      "aspecto": "máscara da novex",
      "opiniao": "amei",
      "polaridade": "POS",
      "confianca": 0.95,
      "categoria_aspecto": "PRODUTO"
    },
    {
      "aspecto": "cabelo",
      "opiniao": "deixa macio sem pesar",
      "polaridade": "POS",
      "confianca": 0.88,
      "categoria_aspecto": "TEXTURA_CABELO"
    }
  ]
}
```

**Entrada (ironia):** `"claro que a proteína salvou meu cabelo 🤡 ficou duro que nem palha"`
**Saída esperada:**
```json
{
  "triplas": [
    {
      "aspecto": "proteína",
      "opiniao": "claro que salvou... ficou duro que nem palha",
      "polaridade": "NEG",
      "confianca": 0.85,
      "categoria_aspecto": "ATIVO_INGREDIENTE"
    }
  ]
}
```

---

## Validação da saída

O `SLMExtractor` aplica estas verificações antes de aceitar uma tripla:

1. `aspecto` e `opiniao` não podem ser vazios
2. `polaridade` deve ser `POS | NEG | NEU | MIX`
3. `confianca` deve ser ≥ `MIN_CONFIDENCE` (padrão: 0.5)
4. Em caso de JSON inválido: até `SLM_MAX_RETRIES` tentativas (padrão: 3)

---

## LoRA fine-tuning do SLM (acúmulo progressivo de conhecimento)

O SLM pode ser afinado com os mesmos dados do BERTimbau, usando LoRA via MLX. Isso permite acumular conhecimento da Embelleze também no Plano B.

### Preparação do dataset

Formato JSONL `chat` (exigido pelo mlx_lm.lora):

```jsonl
{"messages": [{"role": "user", "content": "Extraia ASTE do comentário: 'a máscara da novex reposição de massa não funciona para cabelo cacheado'"}, {"role": "assistant", "content": "{\"triplas\": [{\"aspecto\": \"máscara novex reposição de massa\", \"opiniao\": \"não funciona para cabelo cacheado\", \"polaridade\": \"NEG\", \"confianca\": 0.95, \"categoria_aspecto\": \"RESULTADO_EFICACIA\"}]}"}]}
{"messages": [{"role": "user", "content": "Extraia ASTE do comentário: 'amei o cheiro do óleo de argan, hidratou demais'"}, {"role": "assistant", "content": "{\"triplas\": [{\"aspecto\": \"óleo de argan\", \"opiniao\": \"amei o cheiro\", \"polaridade\": \"POS\", \"confianca\": 0.92, \"categoria_aspecto\": \"ATIVO_INGREDIENTE\"}, {\"aspecto\": \"cabelo\", \"opiniao\": \"hidratou demais\", \"polaridade\": \"POS\", \"confianca\": 0.88, \"categoria_aspecto\": \"RESULTADO_EFICACIA\"}]}"}]}
```

Estrutura de diretório:
```
data/aste_lora/
├── train.jsonl      # 80% dos exemplos anotados
├── valid.jsonl      # 10%
└── test.jsonl       # 10%
```

### Comando de treino

```bash
# Download do modelo base (uma vez)
python -m mlx_lm.convert \
  --hf-path Qwen/Qwen2.5-7B-Instruct \
  --mlx-path ./models/qwen2.5-7b-base \
  -q   # quantiza para 4-bit → ~4.28 GB

# Fine-tuning com LoRA
# --mask-prompt: CRÍTICO — calcula loss só nas completions (assistant), não nos prompts
# --grad-checkpoint: gradient checkpointing — troca compute por memória (essencial no M1 16GB)
# --num-layers 8: fine-tuna 8 das 28 camadas (~4x menos parâmetros treináveis)
mlx_lm.lora \
  --model ./models/qwen2.5-7b-base \
  --train \
  --data ./data/aste_lora/ \
  --iters 600 \
  --batch-size 1 \
  --num-layers 8 \
  --grad-checkpoint \
  --mask-prompt \
  --adapter-path ./models/qwen-aste-adapters/

# Merge dos adapters no modelo base
mlx_lm.fuse \
  --model ./models/qwen2.5-7b-base \
  --adapter-path ./models/qwen-aste-adapters/ \
  --save-path ./models/qwen-aste-fused/
```

**Referência completa:** https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md

### Parâmetros para M1 16GB (4-bit, batch-size 1)

| Parâmetro | Valor | Motivo |
|---|---|---|
| `--batch-size` | 1 | memória limitada em 16GB |
| `--num-layers` | 8 | fine-tuna 8/28 camadas — balance qualidade/memória |
| `--grad-checkpoint` | ativado | gradient checkpointing: troca compute por memória |
| `--mask-prompt` | ativado | **CRÍTICO**: loss só nas completions, não nos prompts |
| `--iters` | 600 | suficiente para 500 exemplos (~1 época completa) |
| `--learning-rate` | 1e-5 | padrão LoRA para instruction-tuning |

### Avaliação do LoRA

Após o merge, avalie com comentários de validação anotados manualmente. Compare:
- Triplas extraídas pelo SLM fine-tuned vs. SLM zero-shot
- Critério: proporção de triplas corretas (aspecto + opinião + polaridade)

O LoRA é opcional — use quando o SLM zero-shot apresentar erros sistemáticos em categorias específicas do Codebook V3.
