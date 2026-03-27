# Diagnóstico — run_corpus_completo.py (2026-03-27)

> Post-mortem do run que processou 891 comentários e não salvou nada.

---

## Resumo executivo

O script completou toda a extração (891/891 comentários, ~12 minutos de API)
e então **travou em uma única linha de sumário com o nome de atributo errado**.
Nenhum dado foi salvo. Nenhuma exceção foi capturada porque o erro aconteceu
**fora** do bloco `try/except` da extração, na agregação final.

---

## Linha do tempo

| Horário | O que aconteceu |
|---------|----------------|
| ~01:07 | Script escrito em `/tmp/run_corpus_completo.py` |
| ~01:07 | 1ª tentativa — background, saiu silenciosamente (processo morto pelo shell) |
| ~01:08 | 2ª tentativa — foreground com `head -30`, também em background, sem output |
| ~01:09 | `PYTHONUNBUFFERED=1`, 3ª tentativa em background |
| ~01:12 | Progresso visível: 650/891 |
| ~01:14 | Processo morto novamente (timeout do background ~5 min) |
| ~01:20 | 4ª tentativa — processo sobreviveu e completou 891/891 |
| ~01:32 | Exit code 1 — script falhou na última etapa (sumário de gate_decisions) |
| ~01:33 | API 529 — Anthropic sobrecarregada; tentativa de diagnóstico manual abortada |

---

## Causa raiz: atributo errado no GateDecision

### O bug (linha 284 do script)

```python
for d in gate_result.decisions:
    gate_decisions[f"{d.gate_class.value}:{d.reason}"] += 1
```

### A estrutura real do GateDecision (extraída do .pyc)

```python
@dataclass
class GateDecision:
    """Decisão do gate para um comentário."""
    classification: GateClass   # ← atributo real
    reason: str
    text_snippet: str = ""
```

O script usava `d.gate_class` — **não existe**. O nome correto é `d.classification`.

### Impacto

- `AttributeError` na linha 284
- Script abortou com exit code 1
- O arquivo `data/corpus_completo_sabiazinho4.json` **nunca foi criado**
- 891 comentários processados → 0 registros salvos

---

## Causa secundária: gate.py não existe mais

O arquivo `src/vozes_da_comunidade/batch/gate.py` foi deletado.
Só existe o `.pyc` compilado:

```
src/vozes_da_comunidade/batch/__pycache__/gate.cpython-312.pyc
```

Python importou o módulo via `.pyc` sem reclamar (comportamento normal do CPython).
Mas a situação é frágil: qualquer upgrade de Python ≥ 3.12 → 3.13 invalida o `.pyc`.

---

## Causa terciária: execução em background foi o padrão errado

O Claude usou o padrão `run_in_background` + `sleep N + tail` repetidamente,
o que é inadequado para jobs de 12 minutos:

| Tentativa | Estratégia | Problema |
|-----------|-----------|---------|
| 1ª | background puro | processo morto silenciosamente |
| 2ª | background + `head -30` | output bufferizado, 0 linhas |
| 3ª | `PYTHONUNBUFFERED=1` + background | morto por timeout (~5 min) |
| 4ª | background com aguardo de notificação | **única que completou** |

O padrão correto para jobs longos é `run_in_background=True` com aguardo de
notificação, sem polling por `sleep`. Funciona, mas é frágil para processos
que o sistema pode matar.

---

## O que foi desperdiçado

Aproximadamente **12 minutos de API Maritaca** e **~900 chamadas sabiazinho-4**,
estimativa de R$ 0,70–1,20 com base nos parâmetros do script.

---

## Fix — uma linha

```python
# Antes (errado):
gate_decisions[f"{d.gate_class.value}:{d.reason}"] += 1

# Depois (correto):
gate_decisions[f"{d.classification.value}:{d.reason}"] += 1
```

---

## O que fazer antes de re-rodar

1. **Aplicar o fix** no script (linha 284)
2. **Recriar gate.py** a partir do `.pyc` antes que o Python quebre
3. **Adicionar save incremental** — salvar parcialmente a cada 100 comentários
   para não perder tudo em caso de falha tardia

### Sugestão de save incremental (inserir após o loop principal):

```python
# Dentro do run_extraction, antes do return, salvar parcial:
if (i+1) % 100 == 0:
    partial_path = PROJECT / 'data' / f'corpus_partial_{i+1}.json'
    with open(partial_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False)
```

---

## Estrutura real do Gate (para referência)

```python
class GateClass(Enum):
    aste_ready      = "aste_ready"
    absa_implicit   = "absa_implicit"
    claim_question  = "claim_question"
    off_topic       = "off_topic"

@dataclass
class GateDecision:
    classification: GateClass   # ← NÃO é gate_class
    reason: str
    text_snippet: str = ""

@dataclass
class GateResult:
    aste_ready:     list[dict]
    absa_implicit:  list[dict]
    claim_question: list[dict]
    off_topic:      list[dict]
    decisions:      list[GateDecision]
```

---

## Ações pendentes

- [ ] Corrigir `d.gate_class` → `d.classification` em `run_corpus_completo.py`
- [ ] Recriar `gate.py` a partir do `.pyc` (decompile ou reescrever)
- [ ] Adicionar save incremental ao script
- [ ] Re-rodar

---

*Gerado em 2026-03-27 por análise post-mortem do session JSONL.*
