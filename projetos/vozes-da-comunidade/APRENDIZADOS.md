# Aprendizados — Vozes da Comunidade

> **Para o Claude:** ao iniciar uma sessão neste projeto, leia este arquivo antes de qualquer ação.
> Ele registra raciocínios críticos, erros evitados e decisões não óbvias que não aparecem no código.

---

## Como ler este arquivo

Cada entrada tem:
- **O que foi descoberto** — o fato técnico
- **Por que importa** — o que teria quebrado sem esse conhecimento
- **Onde está no código** — localização para referência rápida

---

## Sessão — Março/2026: implementação dos extratores ASTE

### 1. `process_text()` — não `.extract()`

**Descoberto em:** exploração do código DINAMICA-ABSA (`full_pipeline.py`)

O método principal do `DINAMICA_ABSAPipeline` é `process_text(text)`.
Não existe `.extract()`. Se chamado, resulta em `AttributeError` imediato.

**Por que importa:** o nome `.extract()` é intuitivo — qualquer desenvolvedor escreveria assim. Só a leitura direta do código revelou o nome correto.

**Onde está:** `src/extractors/bertimbau.py` — método `extract()` e `batch_extract()`

---

### 2. Checkpoint loading — não `from_pretrained()`

**Descoberto em:** exploração do código DINAMICA-ABSA

O DINAMICA-ABSA não tem `from_pretrained()`. O carregamento correto é:
```python
pipeline = DINAMICA_ABSAPipeline(
    model_name="neuralmind/bert-base-portuguese-cased",
    checkpoint_dir=model_path,   # diretório com .pt por componente
)
```

O `checkpoint_dir` aponta para um diretório com arquivos separados:
`aspect_extractor.pt`, `opinion_extractor.pt`, `polarity_classifier.pt`, `pair_matcher.pt`

**Por que importa:** `from_pretrained()` é padrão HuggingFace — parecia óbvio. O DINAMICA-ABSA tem interface própria diferente.

**Onde está:** `src/extractors/bertimbau.py` — método `_load_pipeline()`

---

### 3. `neuralmind/bert-base-portuguese-uncased` não existe

**Descoberto em:** pesquisa HuggingFace neuralmind

Só existem duas variantes do BERTimbau:
- `neuralmind/bert-base-portuguese-cased` (110M)
- `neuralmind/bert-large-portuguese-cased` (335M)

**Não existe versão uncased.** Qualquer referência a uncased em código ou doc está errada.

**Por que importa:** o erro só aparece no momento do download — falha silenciosa ou modelo errado carregado.

**Onde está:** `docs/PLANO_A_BERTIMBAU.md`

---

### 4. `do_lower_case=False` no tokenizador BERTimbau é obrigatório

**Descoberto em:** pesquisa HuggingFace token classification

```python
tokenizer = AutoTokenizer.from_pretrained(
    "neuralmind/bert-base-portuguese-cased",
    do_lower_case=False,   # NÃO omitir
)
```

Sem esse parâmetro, o tokenizador normaliza para minúsculas e corrompe diacríticos (`ã`, `é`, `ç`) antes de tokenizar. Em PT-BR informal com `AMEI`, `HORRÍVEL`, `não` — o impacto é direto na qualidade de extração.

**Por que importa:** falha silenciosa — o código roda sem erro, mas o modelo recebe texto degradado.

**Onde está:** `docs/PLANO_A_BERTIMBAU.md` — seção Gotchas críticos

---

### 5. ollama: `format=schema` vs `format="json"` — diferença crítica

**Descoberto em:** pesquisa GitHub ollama

`format="json"` garante JSON válido sintaticamente.
`format=PydanticModel.model_json_schema()` garante JSON válido **E** tipos/enums corretos.

Com `format="json"`, o modelo pode retornar `"polaridade": "POSITIVE"` ou `"negativo"` — o código precisaria normalizar. Com schema Pydantic, o modelo fisicamente não consegue gerar valores fora de `"POS"|"NEG"|"NEU"|"MIX"` (Literal).

**Por que importa:** sem schema, a pipeline de parsing falharia intermitentemente em produção com comentários ambíguos.

**Onde está:** `src/extractors/slm.py` — classe `_ASTESchema`, método `_call_ollama()`

---

### 6. LoRA MLX: `--mask-prompt` é crítico

**Descoberto em:** pesquisa GitHub ml-explore/mlx-lm (LORA.md)

Sem `--mask-prompt`, o MLX calcula a loss sobre o prompt inteiro (pergunta + resposta). O modelo aprende a reproduzir os próprios prompts, não a gerar triplas ASTE. O treino termina sem erro mas o modelo fine-tuned não aprende nada útil.

Com `--mask-prompt`, a loss é calculada apenas sobre a completion (resposta do assistant).

Parâmetros corretos para M1 16GB:
```bash
mlx_lm.lora \
  --num-layers 8 \      # 8/28 camadas — não 4 (muito conservador)
  --grad-checkpoint \   # gradient checkpointing: troca compute por memória
  --mask-prompt \       # CRÍTICO: loss só nas completions
  --batch-size 1
```

**Por que importa:** falha silenciosa — o fine-tuning parece funcionar, mas o modelo resultante é inútil para extração.

**Onde está:** `docs/PLANO_B_SLM.md` — seção LoRA fine-tuning

---

### 7. `processing_class=` — API v5.x do HuggingFace Trainer

**Descoberto em:** pesquisa HuggingFace Trainer API

O parâmetro `tokenizer=tokenizer` no Trainer foi deprecado. A API v5.x usa `processing_class=tokenizer`. Código com o parâmetro antigo ainda funciona mas emite warnings que viram erros em versões futuras.

**Onde está:** `docs/PLANO_A_BERTIMBAU.md` — script de fine-tuning

---

## Convenções deste projeto

- **Motor de extração:** `ASTE_BACKEND=slm` no `.env` por padrão (funciona imediatamente). Mudar para `bertimbau` quando o checkpoint fine-tuned estiver disponível.
- **Fallback automático:** `build_extractor()` em `src/extractors/__init__.py` — se BERTimbau não estiver pronto, usa SLM com aviso no log. Não quebra.
- **Não duplicar DINAMICA-ABSA:** importar como dependência via `DINAMICA_ABSA_PATH` no `.env`. ADR-001.
- **Corpus:** 4.802 comentários JSON em `.../kimi/package/user_input_files/`
- **Schema canônico:** `MODELO_JSON_EXPLORATORIO_TCC_V1.json` em `.../dinamica_absa/docs/`
