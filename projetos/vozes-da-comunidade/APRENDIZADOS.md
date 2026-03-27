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

---

## Sessão — Março/2026: implementação do pipeline batch e indicadores

### 8. Estrutura do pacote — `src/` mapeado como `vozes_da_comunidade`

**Descoberto em:** revisão do pyproject.toml após criar a CLI

O diretório `src/` é plano (sem subdiretório `vozes_da_comunidade/`). O mapeamento correto no `pyproject.toml`:

```toml
[tool.setuptools.packages.find]
where = ["."]
include = ["vozes_da_comunidade*"]

[tool.setuptools.package-dir]
"vozes_da_comunidade" = "src"
```

Isso permite que `from vozes_da_comunidade.batch import BatchPipeline` funcione sem mover os arquivos.

**Por que importa:** `[tool.setuptools.package-dir] "" = "src"` (padrão comum) não funciona quando o nome do pacote é diferente do diretório.

**Onde está:** `pyproject.toml`

---

### 9. `_raw_chunk_text` não pode ser campo de `ConsumerIntelligenceOutput`

**Descoberto em:** implementação do `formatter.py`

Tentativa inicial: adicionar `_raw_chunk_text` como campo extra ao construtor de `ConsumerIntelligenceOutput` para carregar o texto do Warm Store. Falha: o dataclass não tem esse campo.

Solução limpa: `_search_warm_store()` retorna `list[str]` (chunk texts) diretamente — não tenta reconstruir o dataclass. `_collect_pattern_texts()` retorna `list[str]` em ambos os caminhos (Warm Store ou outputs diretos serializados via `_output_to_text()`). A função `_synthesize_with_haiku()` só precisa de texto.

**Por que importa:** forçar retornos heterogêneos em uma mesma função (`list[ConsumerIntelligenceOutput | str]`) cria bugs silenciosos na serialização para o prompt.

**Onde está:** `src/synthesis/formatter.py` — funções `_collect_pattern_texts()` e `_search_warm_store()`

---

### 10. Flush para o Warm Store usa `vector_store.add()` — não `memory_manager.post_briefing_flush()`

**Descoberto em:** leitura da API da Memória Viva

`MemoryManager.post_briefing_flush()` é para briefings de produto (Hot Store + Warm Store + Cold Store). Para dados do corpus TikTok, o correto é usar `SQLiteVectorStore.add()` diretamente com `collection="vozes_comunidade"`.

**Por que importa:** `post_briefing_flush()` espera campos de briefing (thread_id, iam_score, etc.) que não existem no contexto do Vozes da Comunidade.

**Onde está:** `src/memory/flush.py` — função `_flush_to_warm_store()`

---

---

## Sessão — Março/2026: primeiro teste real com corpus TikTok

### 11. O corpus real NÃO tem `interaction_type` — é produzido pelo pipeline kimi

**Descoberto em:** inspeção do corpus antes de rodar o batch

O corpus bruto (4 arquivos JSON, 4.804 comentários) não tem `interaction_type`, `netnography`, `eligibility` nem `text_for_model`. Esses campos são adicionados pelo pipeline de processamento do kimi (DINAMICA-ABSA/TikTokSchemaNormalizer).

O Router original retornava `eligibility.get("is_eligible", False)` como fallback → rejeitava 100% dos comentários.

**Correção aplicada:** fallback para heurística de comprimento de texto (≥10 chars) quando os campos do schema V1 estão ausentes.

**Por que importa:** todo novo corpus bruto da coleta vai ter esse problema. Sem a correção, o pipeline produz zero triplas sem erro visível.

**Onde está:** `src/vozes_da_comunidade/batch/router.py` — método `_is_relevant()`

---

### 12. `PN_THRESHOLD=0.35` é matematicamente impossível com n<50

**Descoberto em:** resultado vazio de indicadores no teste de 50 comentários

`PN = (freq/total_comments) × intensidade_neg`. Com n=50, um aspecto precisaria aparecer 18+ vezes (36% dos comentários) para ultrapassar PN=0.35. Na prática impossível.

O threshold foi projetado para o corpus completo (4.802 comentários), onde padrões reais emergem com frequência significativa. Com o corpus completo, um aspecto com 1.700+ menções atinge PN=0.35 — isso é realista.

**Ação:** Adicionar `PN_THRESHOLD` e `AP_THRESHOLD` ao `config.py` como variáveis de ambiente (default 0.35 para produção, usar 0.03–0.05 para testes com amostras pequenas).

**Onde está:** `src/vozes_da_comunidade/indicators/calculator.py` — constantes `_PN_THRESHOLD`, `_AP_THRESHOLD`

---

### 13. Segmentação HNR inoperante com corpus bruto

**Descoberto em:** todos os 50 comentários classificados como "indefinido × indefinido"

`ctx_from_comment()` infere HNR via `netnography.native_terms` e `netnography.cultural_markers` — campos que não existem no corpus bruto. Resultado: segmento sempre "indefinido".

**Ação necessária:** implementar `_infer_hnr_from_text(text)` que analisa o próprio texto do comentário com lookup de keywords. Pode ser simples e já desbloquearia a segmentação para o corpus atual.

**Onde está:** `src/vozes_da_comunidade/types.py` — função `ctx_from_comment()`

---

### 14. Qwen2.5:3b: taxa de qualidade ~40–47%; hallucination em ~20% dos casos

**Descoberto em:** avaliação manual de 15 triplas do teste

Padrões de erro identificados:
1. **Opinião = Aspecto** (hallucination): quando o comentário não tem opinião explícita, o SLM duplica o aspecto como opinião. Ex: `[NEU] 'novex reposição de massa' → 'novex reposição de massa'`. Ocorre em ~20% dos casos.
2. **Perguntas retóricas como afirmações**: "Reconstrução em excesso não deixa o cabelo quebradiço?" → `[POS]`. O SLM não reconhece a estrutura de pergunta. Ocorre com textos terminados em `?`.
3. **Entidades off-topic** (criador, pessoas): "Alan tá bonito 👀" → `[POS] 'Alan'`. O prompt precisa instruir explicitamente a ignorar menções a pessoas.
4. **Typos nos aspectos**: "repostação de massa" (erro ortográfico do SLM) em vez de "reposição de massa".

**Por que importa:** com 40–50% de qualidade, os indicadores têm ruído considerável. Para briefings de produto, o BERTimbau fine-tuned (meta: 80–90%) não é opcional.

**Onde está:** `src/vozes_da_comunidade/extractors/slm.py` — o prompt pode ser melhorado para mitigar os erros 1–3.

---

### 15. Packaging: `src/vozes_da_comunidade/` é o src-layout correto

**Descoberto em:** ModuleNotFoundError ao instalar o pacote

O `pyproject.toml` original usava `"vozes_da_comunidade" = "src"` no `package-dir`, mas `find_packages` retornava MAPPING vazio porque não havia diretório `vozes_da_comunidade/`. Solução: mover todos os arquivos de `src/` para `src/vozes_da_comunidade/` (src-layout padrão Python).

Também: `build-backend = "setuptools.backends.legacy:build"` não funcionava no conda. Correto: `"setuptools.build_meta"`.

**Por que importa:** a falha é silenciosa — o pacote "instala" mas nenhum import funciona.

**Onde está:** `pyproject.toml`

---

### 16. `load_dotenv()` deve ser chamado no topo de `config.py`

**Descoberto em:** SLM usava `qwen2.5:7b` (default hardcoded) em vez de `qwen2.5:3b` do `.env`

O `config.py` usava `os.getenv()` para todas as configurações mas nunca carregava o arquivo `.env`. Sem `load_dotenv()`, as variáveis do `.env` só funcionam se já estiverem exportadas no shell.

**Onde está:** `src/vozes_da_comunidade/config.py` — primeiras linhas após os imports

---

### 17. Bug: contadores do Router zerados em `run_sample()`

**Descoberto em:** log do batch mostrando "Comentários: 0 total" com 50 extrações bem-sucedidas

O método `run_sample()` em `pipeline.py` coleta comentários sem passar pelo `_process_file()`, então `result.comments_total/accepted/rejected` ficam zerados. As triplas são extraídas corretamente, o bug é apenas nas métricas de exibição.

**Correção:** `run_sample()` deve chamar `self._router.route(comments_sample)` e incrementar os contadores antes de chamar `_process_comments()`.

**Onde está:** `src/vozes_da_comunidade/batch/pipeline.py` — método `run_sample()`, linha ~189

---

---

### 18. Nunca aprovar job de API caro sem validar TODOS os caminhos de código antes

**Descoberto em:** run_corpus_completo.py processou 891 comentários (~12 min, ~R$1) e não salvou nada por um `AttributeError` no sumário final.

O bug estava na linha 284, fora do `try/except` de extração:
```python
gate_decisions[f"{d.gate_class.value}:{d.reason}"] += 1  # d.gate_class não existe
#                   ^^^^^^^^^^
# O atributo real é d.classification (conforme GateDecision no .pyc)
```

**Por que o Claude não viu antes de rodar?** O smoke test (n=50) exercitou apenas a extração. A linha com `d.gate_class` está na fase de agregação final, que só roda depois de todos os 891 comentários. O Claude aprovou o run sem inspecionar o script completo nem testar o caminho de salvamento.

**Regra derivada:** antes de qualquer job com custo real (API paga, tempo > 5 min), rodar um dry-run que percorra 100% dos caminhos do script — incluindo salvamento, agregação e formatação de saída — com n=1 ou dados mockados.

---

### 19. Arquivo .pyc sem .py é armadilha silenciosa

**Descoberto em:** gate.py foi deletado mas o `.pyc` sobreviveu em `__pycache__/`. O script importou o módulo sem erro, mascarando que o código-fonte estava ausente.

Python importa `.pyc` normalmente quando o `.py` não existe. O problema só aparece quando:
- O Python é atualizado (magic number incompatível → `ImportError`)
- Alguém tenta ler ou editar o código e não encontra nada
- O Claude inspeciona o projeto e acha que o módulo não existe

**Regra derivada:** se um import funciona mas o `.py` não existe, checar `__pycache__/`. Recriar o `.py` a partir do `.pyc` (decompile) ou reescrever antes de confiar no módulo.

**Arquivo afetado:** `src/vozes_da_comunidade/batch/gate.py` — recriar antes do próximo run.

---

### 20. Falha tardia sem save incremental = perda total

**Descoberto em:** mesmo run acima — extração completa, 0 registros salvos porque o `json.dump()` só acontecia depois do sumário que travou.

Em qualquer job longo com API externa, salvar parcialmente durante o loop, não só no final. Exemplo mínimo:

```python
if (i + 1) % 100 == 0:
    Path("data/partial.json").write_text(json.dumps(results, ensure_ascii=False))
```

**Regra derivada:** o padrão é "salvar cedo, salvar frequente". O save final pode ter bugs de agregação/sumário — isso não deve apagar o trabalho de extração já feito.

---

### 21. `run_in_background` + `sleep + tail` é padrão frágil para jobs longos

**Descoberto em:** mesmo run — 3 das 4 tentativas morreram antes de completar (timeout do shell, processo morto, output bufferizado).

O Claude usou repetidamente o padrão `Bash(script, run_in_background=True)` seguido de `sleep N && tail`. Problemas:
- Background processes podem ser mortos após ~5 min de inatividade
- Output bufferizado aparece como 0 linhas no `tail`
- Múltiplos processos concorrentes acumulam calls de API

**Padrão correto:** para jobs > 5 min, usar `run_in_background=True` com `PYTHONUNBUFFERED=1` e aguardar a notificação de conclusão sem `sleep` polling. Só uma instância de cada vez.

---

## Convenções deste projeto

- **Motor de extração:** `ASTE_BACKEND=slm` no `.env` por padrão (funciona imediatamente). Mudar para `bertimbau` quando o checkpoint fine-tuned estiver disponível.
- **Fallback automático:** `build_extractor()` em `src/extractors/__init__.py` — se BERTimbau não estiver pronto, usa SLM com aviso no log. Não quebra.
- **Não duplicar DINAMICA-ABSA:** importar como dependência via `DINAMICA_ABSA_PATH` no `.env`. ADR-001.
- **Corpus:** 4.802 comentários JSON em `.../kimi/package/user_input_files/`
- **Schema canônico:** `MODELO_JSON_EXPLORATORIO_TCC_V1.json` em `.../dinamica_absa/docs/`
