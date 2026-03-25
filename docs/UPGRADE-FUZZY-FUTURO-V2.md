# Plano de Upgrade — Fuzzy Matching V2

> Documento de planejamento técnico. Não há código a executar aqui —
> apenas o racional, as opções avaliadas e o plano de implementação
> para uma versão futura do sistema de busca.
>
> Pré-requisito: a V1 (expansão de abreviações PT-BR) deve estar
> estável antes de iniciar esta fase.

---

## Contexto e Motivação

O sistema de busca do Total Recall evoluiu em camadas. A V1 resolve dois dos
três casos de variação linguística que afetam a recuperação via FTS5:

| Caso | V1 resolve? | Mecanismo |
|---|---|---|
| `você` / `vocé` / `voce` | ✅ sim | unicode61 remove diacríticos automaticamente |
| `vc` / `pq` / `hj` (abreviações) | ✅ sim | `_PT_ABBREVIATIONS` + OR-groups no FTS5 |
| `novax` → `novex` (erro de digitação) | ❌ não | troca de vogal não é diacrítico |
| `sqilte` → `sqlite` (transposição) | ❌ não | tokens completamente diferentes |
| `chromdb` → `chromadb` (letra faltando) | ❌ não | idem |

A V1 resolve variações *sistemáticas* e *previsíveis* — diacríticos e abreviações
conhecidas. O que ela não resolve são erros de digitação *idiossincrásicos*: uma
vogal trocada, uma letra transposta, um fragmento de nome técnico.

Esses erros são especialmente frequentes em três categorias dentro do corpus do
Total Recall:

- **Nomes de tecnologias**: `sqllite`, `postrgres`, `chroma-db`, `sqlite_vec`
- **Nomes de projetos**: `memoria viva` → `memoria-viva`, `memoriaviva`
- **Identificadores de código**: `session_id` → `sessionid`, `sessionId`

O fuzzy matching resolve exatamente essa lacuna: dado um token com erro de
digitação, encontra tokens suficientemente similares no vocabulário indexado
e expande a query com OR antes de passar para o FTS5.

---

## Quatro Abordagens Técnicas Avaliadas

### Opção A — `spellfix1` (extensão SQLite)

**O que é**: extensão oficial do SQLite para busca fonética e por distância
de edição. Compilada como `.so` e carregada via `conn.load_extension()`.

**Prós**:
- Nativa ao ecossistema SQLite — sem dependência Python adicional
- Suporta distância de edição (Levenshtein) e busca fonética (Soundex-like)
- Performática para corpora pequenos a médios

**Contras**:
- Requer compilação manual a partir do código-fonte do SQLite (`spellfix.c`)
- Não está disponível em binários padrão do Python — atrito de instalação
- Exige uma tabela de vocabulário separada mantida em sincronia com o índice
- Não é `pip install`-able; distribuição é problema real

**Veredito**: descartada. O atrito de compilação e distribuição contradiz o
princípio de instalação simples do Total Recall.

---

### Opção B — Índice de Trigramas

**O que é**: indexar todos os tokens do corpus como sequências de 3 caracteres.
"sqlite" produz `{sql, qli, lit, ite}`. Busca por interseção de trigramas entre
a query e o vocabulário.

**Prós**:
- Tolerante a qualquer tipo de erro de digitação sem dependência externa
- Consultável via SQL puro — sem Python adicional
- Conceito bem estabelecido em sistemas de busca (usado pelo PostgreSQL pg_trgm)

**Contras**:
- Requer tabela adicional no banco — nova migração de schema
- A tabela de trigramas deve ser reconstruída a cada indexação de novos chunks
- Alta taxa de falsos positivos para tokens curtos (< 4 chars)
- Implementação não-trivial no contexto SQLite + sqlite-vec + WAL

**Veredito**: tecnicamente sólido, mas o custo de schema migration e manutenção
contínua não se justifica para o volume atual. Reconsiderar se o corpus superar
50.000 chunks.

---

### Opção C — `rapidfuzz` em Python (recomendada)

**O que é**: biblioteca Python de fuzzy string matching baseada em distância de
edição (Levenshtein, Jaro-Winkler, token set ratio). Opera inteiramente no lado
Python, como pré-processamento da query — sem qualquer mudança de schema.

**Fluxo proposto**:

```
query: "novax pasta projetos"
         │
         ▼ _get_fts_vocabulary(conn)
         │   extrai tokens únicos do índice FTS5
         │   (via chunks_fts_vocab virtual table)
         │
         ▼ para cada token da query:
         │   buscar similares com rapidfuzz (threshold ≥ 0.85)
         │   "novax" → match: "novex" (similarity: 0.90)
         │   "pasta" → sem match acima do threshold
         │   "projetos" → sem match (token correto)
         │
         ▼ construir query expandida:
         │   ("novax" OR "novex") "pasta" "projetos"
         │
         ▼ FTS5 MATCH → resultados
```

**Prós**:
- `pip install rapidfuzz` — instalação trivial
- **Zero mudança de schema** — o banco atual permanece idêntico
- Controle granular sobre threshold, máximo de expansões e comprimento mínimo
- Implementação concentrada em dois métodos em `vector_store.py`
- Não interfere com a expansão de abreviações V1 — camadas independentes
- Graceful degradation: se `rapidfuzz` não estiver instalado, cai para V1

**Contras**:
- Carregamento do vocabulário FTS5 a cada busca (mitigável com cache em memória)
- Latência adicional estimada: 50–100ms para vocabulários de ~5.000 tokens únicos
- Threshold exige calibração — muito baixo gera ruído, muito alto perde cobertura

**Veredito**: melhor custo-benefício. Recomendada para a V2.

---

### Opção D — Embedding como Fallback Implícito (já existe)

**O que é**: o motor vetorial (qwen3-embedding:4b) já opera em paralelo com o
FTS5. Para erros de digitação, o vetor pode recuperar semanticamente o que o
FTS5 perdeu — desde que o contexto ao redor do token seja suficientemente rico.

**Prós**:
- Já implementado — custo adicional zero
- Funciona bem para erros em palavras comuns de alta frequência

**Contras**:
- Para nomes técnicos curtos (`novex`, `spellfix1`, `sqlite_vec`), o contexto
  raramente compensa a distância de edição no espaço vetorial
- Comportamento imprevisível: o usuário não sabe antecipadamente quando vai
  funcionar e quando vai falhar

**Veredito**: complemento valioso da arquitetura, não solução para o problema
de erros de digitação. Manter como está; não contar com ele para este caso.

---

## Recomendação: Opção C com `rapidfuzz`

### Racional da escolha

A decisão segue os mesmos princípios que guiaram o design do Total Recall
desde o início: preferir soluções que não aumentem a superfície de operação
do sistema sem necessidade proporcional.

1. **Zero impacto no schema** — o banco de dados não muda; nenhuma migração necessária
2. **Instalação pip-native** — sem compilação, sem extensões C
3. **Camadas independentes** — V1 (abreviações) e V2 (fuzzy) não se interferem
4. **Threshold configurável** — via `TOTAL_RECALL_FUZZY_THRESHOLD`, ajustável por ambiente
5. **Reversível** — se o fuzzy introduzir degradação, basta não instalar `rapidfuzz`

---

## Plano de Implementação

### Fase 1 — Dependência e configuração

```toml
# pyproject.toml — adicionar à lista de dependencies
"rapidfuzz>=3.0",
```

```python
# config.py — adicionar
FUZZY_THRESHOLD = float(os.getenv("TOTAL_RECALL_FUZZY_THRESHOLD", "0.85"))
FUZZY_MAX_EXPANSIONS = int(os.getenv("TOTAL_RECALL_FUZZY_MAX_EXPANSIONS", "3"))
FUZZY_MIN_TOKEN_LENGTH = int(os.getenv("TOTAL_RECALL_FUZZY_MIN_TOKEN_LENGTH", "4"))
```

### Fase 2 — Extração de vocabulário do FTS5

```python
# vector_store.py — novo método
def _get_fts_vocabulary(self, conn) -> set[str]:
    """
    Extrai tokens únicos do índice FTS5 via chunks_fts_vocab.
    Resultado cacheado em memória por 60s para evitar query repetida.
    """
    # SELECT term FROM chunks_fts_vocab WHERE col='content'
    # Filtrar tokens com len >= FUZZY_MIN_TOKEN_LENGTH
    # Cache com timestamp para TTL
    ...
```

A virtual table `chunks_fts_vocab` é criada automaticamente pelo FTS5 e contém
todos os tokens únicos do índice — é a fonte de verdade do vocabulário atual.

### Fase 3 — Expansão fuzzy

```python
# vector_store.py — novo método
def _expand_fuzzy(self, query: str, conn) -> str:
    """
    Para cada token da query com len >= FUZZY_MIN_TOKEN_LENGTH,
    busca variantes próximas no vocabulário FTS5.
    Tokens com similaridade >= FUZZY_THRESHOLD são adicionados como OR.
    """
    from rapidfuzz import process, fuzz
    vocabulary = self._get_fts_vocabulary(conn)
    words = query.lower().split()
    parts = []

    for word in words:
        clean = word.strip(".,!?;:")
        if len(clean) < FUZZY_MIN_TOKEN_LENGTH:
            parts.append(f'"{clean}"')
            continue

        matches = process.extract(
            clean, vocabulary,
            scorer=fuzz.ratio,
            limit=FUZZY_MAX_EXPANSIONS,
            score_cutoff=FUZZY_THRESHOLD * 100,
        )

        if matches and matches[0][0] != clean:
            variants = [clean] + [m[0] for m in matches if m[0] != clean]
            group = " OR ".join(f'"{v}"' for v in variants)
            parts.append(f"({group})")
        else:
            parts.append(f'"{clean}"')

    return " ".join(parts)
```

### Fase 4 — Integração em `keyword_search()`

A ordem de processamento na pipeline de busca keyword passa a ser:

```
query original
    │
    ▼ _expand_abbreviations()   ← V1: vc→você, pq→porque
    │
    ▼ _expand_fuzzy()           ← V2: novax→novex, sqilte→sqlite
    │
    ▼ _sanitize_fts_query()     ← sanitização final (fallback)
    │
    ▼ FTS5 MATCH
```

### Fase 5 — Atualizar `total-recall status`

Adicionar linha de diagnóstico:

```
Fuzzy matching: ativo (threshold: 0.85, min_token: 4)
```

ou, se `rapidfuzz` não estiver instalado:

```
Fuzzy matching: inativo (instale rapidfuzz>=3.0 para habilitar)
```

---

## Testes Obrigatórios

### Casos que devem passar após a V2

```bash
# Troca de vogal
total-recall search "novax"           # → encontra chunks com "novex"
total-recall search "sqilte vec"      # → encontra chunks com "sqlite-vec"

# Letra faltando
total-recall search "chromdb"         # → encontra chunks com "chromadb"
total-recall search "sqlite-ve"       # → encontra chunks com "sqlite-vec"

# Nomes de projetos sem hífen
total-recall search "memoriaviva"     # → encontra chunks com "memoria-viva"
total-recall search "total recall"    # → encontra chunks com "total-recall"
```

### Casos de regressão que não podem piorar

```bash
# Buscas exatas devem continuar funcionando
total-recall search "sqlite-vec"
total-recall search "qwen3-embedding"
total-recall search "como decidimos sobre a arquitetura"

# Abreviações V1 devem continuar funcionando
total-recall search "vc decidiu"
total-recall search "pq escolhemos sqlite"
```

---

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Falsos positivos para tokens curtos | Alta | Médio | `FUZZY_MIN_TOKEN_LENGTH=4` exclui ≤ 3 chars |
| Latência perceptível em buscas | Média | Baixo | Cache de vocabulário com TTL de 60s |
| Expansão excessiva polui resultados | Média | Médio | `FUZZY_MAX_EXPANSIONS=3` limita variantes |
| Degradação em buscas exatas | Baixa | Alto | Fuzzy só expande se match ≠ token original |
| Threshold muito conservador | Baixa | Baixo | Default 0.85 calibrável via env var |
| `rapidfuzz` não instalado | Baixa | Nulo | Graceful degradation: fuzzy silenciosamente desabilitado |

---

## Quando NÃO aplicar fuzzy

O fuzzy matching introduz risco de expansão indevida nas seguintes categorias,
que devem ser explicitamente excluídas da pipeline:

- **UUIDs e session IDs**: `9739fab2` não deve nunca ser expandido
- **Tokens de 1–3 caracteres**: `db`, `id`, `vc` — já cobertos pela V1 ou irrelevantes para fuzzy
- **Operadores FTS5**: `AND`, `OR`, `NOT`, `NEAR` — não devem ser expandidos
- **Tokens já processados pela V1**: abreviações expandidas não devem passar pelo fuzzy
- **Nomes de arquivos com extensão**: `config.py` — o tokenizador FTS5 já separa no `.`

A regra prática: aplicar fuzzy apenas sobre tokens com `len >= FUZZY_MIN_TOKEN_LENGTH`
que não sejam reconhecidos pela V1 e não correspondam a padrões de UUID.

---

## Critérios de Aceitação

A V2 é considerada pronta para merge quando:

1. `total-recall search "sqilte"` retorna chunks contendo "sqlite"
2. `total-recall search "novax"` retorna chunks contendo "novex"
3. Buscas exatas existentes não regridem em precisão ou latência percebida
4. `total-recall status` exibe o estado do fuzzy e o threshold ativo
5. O sistema inicializa normalmente se `rapidfuzz` não estiver instalado
6. Os testes de regressão da V1 (abreviações) continuam passando

---

## Dependências

| Pacote | Versão mínima | Propósito |
|---|---|---|
| `rapidfuzz` | `>=3.0` | Distância de edição e matching fuzzy |

Nenhuma mudança de schema de banco de dados. Nenhuma nova tabela. Nenhuma
mudança nos modelos de embedding ou na dimensão dos vetores.

---

*Pré-requisito: V1 (expansão de abreviações PT-BR) estável em produção.*
*Referência: `src/total_recall/vector_store.py`, `src/total_recall/config.py`*
