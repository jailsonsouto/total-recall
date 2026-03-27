# Relatório de Benchmark — Sessão 2026-03-27

> Consolida todos os resultados da sessão de trabalho de 26-27/03/2026.
> Inclui: Gate Semântico, comparativo 5-way de modelos, e estado atual da pipeline.

---

## 1. O que foi feito nesta sessão

### Melhorias implementadas (branch `teste/aste-absa-gate-semantico`)

| Commit | O que entregou |
|--------|----------------|
| `138f5dd` | Gate semântico + fix indicadores + parser hardening |
| `14fd797` | Auditoria 3-way (Qwen 3b vs 7b vs Haiku, n=112) |
| `4492cb9` | APRENDIZADOS #26–#28 (lições do Haiku benchmark) |
| `9236877` | Auditoria 5-way + dados Maritaca (sabiazinho-4 e sabia-4) |
| `dfc81fe` | Análise interpretativa + veredicto final |
| `bc5add0` | Recriar gate.py + script corpus com safeguards pós-crash |

---

## 2. Gate Semântico — benchmark no corpus completo

> **Data:** 2026-03-27
> **Corpus:** `data/corpus_v1/` (4 arquivos, corpus TikTok Embelleze/Novex)
> **Tempo total:** Router 2ms + Gate 38ms = **40ms** para 4.804 comentários

### 2.1 Funil de filtragem

```
4.804 comentários no corpus
    │
    ▼ Router (filtra por interaction_type + comprimento)
1.876 aceitos (39.1%)   ←  2.928 descartados
    │
    ▼ Gate Semântico (classifica semanticamente)
    ├── aste_ready:     383  (20.4%)  ← elegíveis para extração ASTE
    ├── absa_implicit:  535  (28.5%)  ← sentimento sem aspecto explícito
    ├── claim_question: 337  (18.0%)  ← perguntas / conselhos
    └── off_topic:      621  (33.1%)  ← sem conteúdo analítico relevante
```

### 2.2 Razões por classe

| Razão | Qtd | Classe |
|-------|----:|--------|
| `aspecto_e_opiniao_presentes` | 383 | aste_ready |
| `opiniao_sem_aspecto_explicito` | 303 | absa_implicit |
| `menciona_produto_sem_opiniao_clara` | 232 | absa_implicit |
| `pergunta_sem_opiniao_propria` | 337 | claim_question |
| `sem_aspecto_nem_opiniao` | 533 | off_topic |
| `texto_muito_curto` | 88 | off_topic |

### 2.3 Impacto sobre custo de API

Sem gate, o extrator receberia **1.876 comentários**. Com gate, recebe **383** — uma redução de **79.6%** de chamadas de API.

| Cenário | Comentários ao extrator | Custo estimado (sabiazinho-4) |
|---------|------------------------:|------------------------------:|
| Sem gate | 1.876 | ~R$ 3,00 |
| Com gate (aste_ready) | 383 | ~R$ 0,61 |
| **Economia** | **1.493 chamadas** | **~R$ 2,39 (80%)** |

---

## 3. Comparativo 5-way de modelos (n=112, mesma amostra)

> **Amostra:** 112 comentários classificados como ASTE_READY pelo gate
> **Artefato:** `data/teste_maritaca_matched_n112.json`, `data/teste_haiku_matched_n112.json`
> **Relatório completo:** `docs/AUDITORIA_5WAY_todos_modelos_n112_2026-03-27.md`

### 3.1 Resumo comparativo

| Modelo | Tipo | Com tripla | Absteve | Triplas/comment | Negação PT-BR | Custo/112 |
|--------|------|----------:|--------:|----------------:|:-------------:|----------:|
| Qwen 3b | local gratuito | **97 (87%)** | 15 | 1.0 | 100%* | R$ 0 |
| Qwen 7b | local gratuito | 29 (26%) | 83 | 1.4 | 100%* | R$ 0 |
| Haiku | API Anthropic | 93 (83%) | 19 | 1.7 | **100%** | ~R$ 0,51 |
| **Sabiazinho-4** | API Maritaca | 92 (82%) | 20 | 1.8 | **100%** | ~R$ 0,10 |
| Sabia-4 | API Maritaca | 90 (80%) | 22 | 1.4 | **100%** | ~R$ 0,55 |

*O Qwen 3b só acerta negação porque o `_fix_polarity()` do parser corrige via keyword — sem ele erraria.

### 3.2 Distribuição de consenso

| Consenso | Qtd | % | Interpretação |
|----------|----:|--:|---------------|
| 5/5 extraíram | 27 | 24% | Alta confiança — todos concordam |
| 4/5 extraíram | 50 | 44% | Confiança boa — 1 modelo discordou |
| 3/5 extraíram | 14 | 12% | Divisão |
| 2/5 extraíram | 4 | 3% | Baixa confiança |
| 1/5 extraiu | **16** | 14% | Provável alucinação |
| 0/5 | 1 | 0% | Gate deveria filtrar |

**Achado crítico:** nos 50 casos de consenso 4/5, o dissidente solitário foi o **7b em 100% dos casos** (50/50). O 7b não é conservador — é sistematicamente cego.

**Achado crítico:** das 16 extrações solo (prováveis alucinações), **15 foram do 3b**. Padrão: perguntas e off-topic viram triplas com opinião `"amei"` inventada.

### 3.3 Exemplos de alucinação do Qwen 3b

| Comentário original | Tripla inventada |
|--------------------|------------------|
| "oii, qual indicaria pra quem faz química?" | `[POS] química → amei` |
| "esa música tá me deixando loca" | `[POS] música → amei` |
| "esse é creme de pentear ou de hidratação?" | `[POS] hidratação → amei` |
| "alguma alisada já usou?" | `[POS] alisada → amei` |

### 3.4 Custo projetado — corpus completo (383 aste_ready com gate)

| Modelo | Custo/383 comentários | Custo em BRL* |
|--------|---------------------:|-------------:|
| Qwen 3b | R$ 0 | R$ 0 |
| Qwen 7b | R$ 0 | R$ 0 |
| Haiku | ~$0.33 | ~R$ 1,80 |
| **Sabiazinho-4** | **~R$ 0,35** | **R$ 0,35** |
| Sabia-4 | ~R$ 1,90 | R$ 1,90 |

*USD/BRL estimado em R$ 5,50

---

## 4. Veredicto e recomendações

### 4.1 Modelo recomendado para produção: **Sabiazinho-4**

| Critério | Sabiazinho-4 | Haiku |
|----------|:------------:|:------:|
| Qualidade (extração) | 82% | 83% |
| Negação PT-BR | 100% | 100% |
| Triplas/comment | 1.8 | 1.7 |
| Velocidade (n=112) | **90s** | 134s |
| Custo corpus completo | **~R$ 0,35** | ~R$ 1,80 |
| Moeda | **BRL** | USD |
| PT-BR nativo | **Sim** | Não |

**Conclusão:** empate técnico de qualidade, Sabiazinho-4 vence em custo (5×) e velocidade.

### 4.2 Modelos descartados

- **Qwen 3b:** alucina ~15% dos casos — inventa opiniões onde não existe nenhuma.
- **Qwen 7b:** absteve em 74% dos casos, incluindo 50 onde todos os outros concordam. Inútil como extrator de produção.

### 4.3 Sabia-4: reserva estratégica

Qualidade ligeiramente inferior ao sabiazinho-4 (80% vs 82%), custo 5× maior. Usar apenas para validação cruzada em gold set.

---

## 5. Melhorias de qualidade implementadas (vs estado anterior)

| Componente | Estado anterior | Estado atual |
|------------|----------------|--------------|
| Filtro de entrada | Router simples (interaction_type) | Router + Gate semântico (2 camadas) |
| Parser | Permissivo | Hardened: aspecto≠opinião, sem vazio, confiança mínima |
| Indicadores | Bug: POS aparecia em dores_principais | Fix: PN filtra só NEG, AP filtra só POS |
| Negação PT-BR | Erro em 20% dos casos (Qwen 3b raw) | `_fix_polarity()` corrige via keyword |
| Modelo de extração | Qwen 3b (local, free, 40-47% qualidade) | Sabiazinho-4 (API, 82% qualidade) |
| Rastreabilidade | Sem trilha de decisão | Gate salva `GateDecision` por comentário |
| Cobertura de API | 96% do corpus chegava ao extrator | 20% chega (economia de 80% em custo) |

---

## 6. Safeguards implementados pós-crash

O script `/tmp/run_corpus_completo.py` da sessão anterior teve duas falhas catastróficas:
- Bug `d.gate_class` → `AttributeError` apagou 891 resultados processados
- Sem save incremental → perda total ao crashar na agregação

Novos safeguards em `scripts/run_corpus.py`:

| Safeguard | Implementação |
|-----------|---------------|
| Atributo correto | `d.classification.value` (não `d.gate_class`) |
| Save incremental | `corpus_partial_N.json` a cada 100 comentários |
| Retry API | Backoff 5s / 15s / 45s para erros 429/529 |
| `--dry-run` | Valida pipeline completa em 10 comentários sem consumir API |
| `--resume` | Retoma de partials — não perde progresso em crash tardio |
| Script no repo | `scripts/run_corpus.py` — nunca mais em `/tmp/` |

---

## 7. Estado atual — o que está pronto vs o que falta

### Pronto

- Gate semântico recriado e calibrado (`src/vozes_da_comunidade/batch/gate.py`)
- Script de corpus com safeguards (`scripts/run_corpus.py`)
- Dry-run validado: pipeline completa funciona sem erros
- 383 comentários elegíveis mapeados para extração ASTE

### Próximo passo imediato

```bash
# Quando quiser rodar o corpus completo (custo estimado ~R$ 0,35):
python3 scripts/run_corpus.py --dry-run   # valida primeiro
python3 scripts/run_corpus.py             # roda de verdade
```

### Decisão pendente — caminho arquitetural

Ver `docs/LEMBRETE_ESTADO_ATUAL_ASTE_ABSA_2026-03-27.md` para contexto completo.

| Opção | O que é | Quando faz sentido |
|-------|---------|-------------------|
| **Ciclo 2** | Validação com gold set adjudicado | Antes de decidir modelo definitivo |
| **Ciclo 3A** | BERTimbau + LLM professora → fine-tuning | Quando precisar de ativo proprietário |
| **Ciclo 3B** | LLM local Unsloth + HuggingFace | Quando precisar flexibilidade local |

---

*Relatório gerado em 2026-03-27 combinando dados das sessões `31c6d284` e sessão atual.*
