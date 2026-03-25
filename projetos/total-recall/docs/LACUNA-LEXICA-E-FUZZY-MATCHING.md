# A Lacuna Léxica na Recuperação de Informação
## Um Estudo Aprofundado do Problema que o Fuzzy Matching Resolve

> Documento técnico de nível avançado. Cobre os fundamentos teóricos da
> recuperação de informação lexical, a anatomia do problema de typo tolerance,
> a matemática por trás das métricas de distância de edição, e a arquitetura
> de solução com `rapidfuzz`. Inclui análise comparativa com alternativas —
> em especial a abordagem via reescrita de query por LLM.
>
> Contexto: corpus de 5.672 termos únicos indexados no FTS5 do Total Recall,
> média de 7,1 caracteres por termo, vocabulário predominantemente técnico
> em pt-BR e inglês.

---

## 1. O Problema Fundamental: Vocabulário Mismatch

O problema central da recuperação de informação nunca foi o armazenamento —
foi sempre a correspondência. Dado um corpus de documentos e uma query de um
usuário, a pergunta fundamental é: como identificar quais documentos são
relevantes para aquela query quando as palavras usadas em um não coincidem
exatamente com as palavras no outro?

A literatura clássica de IR chama isso de **vocabulary mismatch problem**.
Ele se manifesta em dois planos distintos:

```
             VOCABULARY MISMATCH
                    │
         ┌──────────┴──────────┐
         │                     │
   SEMÂNTICO              LEXICAL
   "carro" ≠ "automóvel"  "sqlite" ≠ "sqilte"
         │                     │
  Significado diferente,   Significado idêntico,
  palavras diferentes.     ortografia diferente.
         │                     │
  Solução: embeddings      Solução: approximate
  vetoriais (já temos)     string matching (V2)
```

Esta distinção é não-trivial. Sistemas que tratam os dois problemas com a
mesma ferramenta invariavelmente falham em um dos dois. O Total Recall já
resolve o plano semântico com qwen3-embedding:4b — o motor vetorial captura
paráfrases, sinônimos e relações cross-linguais. O plano lexical é o que
permanece em aberto.

O mismatch lexical tem três sub-categorias com características distintas:

| Sub-categoria | Exemplo | Frequência no corpus |
|---|---|---|
| Erros de digitação (typos) | `sqilte` → `sqlite` | Alta em identifiers |
| Variações ortográficas | `database` → `data-base` | Média |
| Abreviações | `vc` → `você` | Alta em pt-BR informal |

A terceira já está resolvida pela V1 (expansão de abreviações via
`_PT_ABBREVIATIONS`). Este documento foca nas duas primeiras.

---

## 2. Por que o BM25/FTS5 Falha em Erros de Digitação

O FTS5 do SQLite usa o algoritmo BM25 (Best Match 25) para ranking. A função
de scoring é:

```
             N - n(q) + 0.5
score(D,Q) = Σ  IDF(qi) × ──────────────────────────────── × TF(qi,D) × (k1+1)
              i  n(q) + 0.5   TF(qi,D) + k1 × (1 - b + b × |D|/avgdl)
```

Onde:
- `IDF(qi)` = log inverso da frequência do documento do termo qi
- `TF(qi, D)` = frequência do termo qi no documento D
- `k1` = parâmetro de saturação de frequência (default ~1.2)
- `b` = parâmetro de normalização por comprimento (default ~0.75)
- `avgdl` = comprimento médio dos documentos no corpus

**O ponto crítico**: se o token `sqilte` não existe no índice, `TF("sqilte", D) = 0`
para todo documento D. Não importa quantas vezes `sqlite` apareça no corpus —
a contribuição do termo à query é zero. O documento que contém 50 ocorrências
de `sqlite` recebe score 0 para a query `sqilte`.

A pipeline de tokenização do FTS5 com `unicode61`:

```
Input: "Sqilte-vec é ótimo"
   ↓
Unicode normalization (NFD)
   ↓
Lowercase: "sqilte-vec é otimo"
   ↓
Remove diacríticos (unicode61): "sqilte-vec e otimo"
   ↓
Tokenização por whitespace/punctuation: ["sqilte", "vec", "e", "otimo"]
   ↓
Índice invertido: { "sqilte": [doc_ids], "vec": [doc_ids], ... }
```

Nenhuma etapa trata transposições de caracteres (`il` → `li`), substituições
(`a` → `e`), ou omissões. O tokenizador simplesmente não vê a relação entre
`sqilte` e `sqlite` — são tokens completamente independentes.

---

## 3. A Matemática da Distância de Edição

### 3.1 Distância de Levenshtein

A distância de Levenshtein d(a, b) é definida como o número mínimo de
operações de edição de caractere único necessárias para transformar a string
`a` em `b`. As operações são: **inserção**, **deleção**, **substituição**.

Formulação recursiva:

```
d(i, 0) = i                              (deletar i caracteres)
d(0, j) = j                              (inserir j caracteres)
d(i, j) = d(i-1, j-1)                   (se a[i] = b[j])
d(i, j) = 1 + min(d(i-1, j),            (deleção)
                  d(i,   j-1),           (inserção)
                  d(i-1, j-1))           (substituição)
```

Aplicando em nosso caso de interesse:

```
  a = "sqilte"  (6 chars)
  b = "sqlite"  (6 chars)

      ""  s  q  l  i  t  e
  ""   0  1  2  3  4  5  6
  s    1  0  1  2  3  4  5
  q    2  1  0  1  2  3  4
  i    3  2  1  1  1  2  3
  l    4  3  2  1  2  2  3   ← transposta "il" → "li"
  t    5  4  3  2  2  2  3
  e    6  5  4  3  3  3  2

  d("sqilte", "sqlite") = 2
```

Levenshtein puro conta a transposição `il↔li` como 2 operações (substituir
`i` por `l` e `l` por `i`). A similaridade normalizada seria:

```
similarity = 1 - d(a,b) / max(|a|, |b|) = 1 - 2/6 = 0.667
```

Com threshold 0.85, esse match seria descartado. Problema real.

### 3.2 Distância de Damerau-Levenshtein

A extensão de Damerau adiciona a operação de **transposição** de dois
caracteres adjacentes como operação única:

```
d(i, j) = 1 + min(d(i-1, j),          (deleção)
                  d(i, j-1),           (inserção)
                  d(i-1, j-1),         (substituição)
                  d(i-2, j-2))         (transposição, se a[i]=b[j-1] e a[i-1]=b[j])
```

Com Damerau-Levenshtein:

```
  "sqilte" → "sqlite"
  Operação: transpor "il" → "li"
  Custo: 1

  similarity = 1 - 1/6 = 0.833
```

Ainda abaixo do threshold 0.85, mas muito mais próximo. E para o caso mais
frequente na prática — uma única letra errada ou faltando:

```
  "chromdb" → "chromadb"  (letra faltando)
  d = 1
  similarity = 1 - 1/8 = 0.875  ✓ (acima do threshold)

  "novax" → "novex"  (vogal trocada)
  d = 1
  similarity = 1 - 1/5 = 0.800  ✗ (abaixo do threshold para strings curtas!)
```

Este último caso revela uma propriedade fundamental: **o threshold absoluto
é sensível ao comprimento da string**. Para strings curtas (≤ 5 chars), uma
única substituição pode baixar a similaridade para 0.80, abaixo do threshold
padrão de 0.85. Para strings longas (≥ 8 chars), a mesma operação permanece
acima do threshold.

### 3.3 Jaro-Winkler — Melhor para Identificadores Técnicos

A métrica de Jaro é formulada especificamente para strings curtas e foi
desenvolvida no contexto de record linkage (deduplicação de registros civis):

```
            ⎧ 0                          se m = 0
jaro(s,t) = ⎨
            ⎩ 1/3 × (m/|s| + m/|t| + (m-t/2)/m)

onde:
  m = número de caracteres correspondentes
  t = número de transposições
  (caracteres são "correspondentes" se iguais e dentro de max(|s|,|t|)/2 - 1 posições)
```

Jaro-Winkler adiciona um prefixo bonus:

```
jaro_winkler(s, t) = jaro(s,t) + p × ℓ × (1 - jaro(s,t))

onde:
  ℓ = comprimento do prefixo comum (máx 4)
  p = constante de escala (default 0.1)
```

Para identificadores técnicos com prefixo comum (`qwen3-embedding` vs
`qwen3-embeding`), Jaro-Winkler é superior ao Levenshtein puro porque
valoriza explicitamente o prefixo comum — que em nomes de bibliotecas
e projetos é invariavelmente o elemento mais discriminativo.

### 3.4 A Métrica que o rapidfuzz Usa: WRatio

O `rapidfuzz` implementa o **WRatio** (Weighted Ratio) — uma meta-métrica
adaptativa que seleciona a melhor sub-métrica baseada nas características
das strings:

```python
def WRatio(s1, s2):
    # Normalização por comprimento
    len_ratio = max(len(s1), len(s2)) / min(len(s1), len(s2))

    # Para strings de comprimento similar e curtas:
    if len_ratio < 1.5:
        base = ratio(s1, s2)  # Levenshtein normalizado

        # Se strings longas, considerar match parcial
        if max(len(s1), len(s2)) > 10:
            partial = partial_ratio(s1, s2)
            base = max(base, partial * 0.995)

    # Para strings com diferença grande de comprimento:
    else:
        base = partial_ratio(s1, s2) * 0.90

    # Token-based adjustments
    if len(s1.split()) > 1 or len(s2.split()) > 1:
        t_sort = token_sort_ratio(s1, s2) * 0.95
        t_set = token_set_ratio(s1, s2) * 0.90
        base = max(base, t_sort, t_set)

    return base
```

Para os casos de interesse no Total Recall (tokens únicos técnicos de 4-12
caracteres), o WRatio degenera para o Levenshtein normalizado simples — que
é computacionalmente eficiente e semanticamente correto para esse perfil.

---

## 4. O Desafio Computacional — Por que Não é Trivial

### 4.1 Complexidade Ingênua

Comparar um token de query contra todos os N termos do vocabulário FTS5:

```
T_naive = O(N × L²)

onde:
  N = 5.672 termos únicos no corpus atual
  L = 7,1 chars (comprimento médio)

T_naive ≈ 5.672 × 7,1² ≈ 286.000 operações por token de query
Para query de 4 tokens: ~1,14 milhões de operações
```

Com a implementação C++ do rapidfuzz (não Python puro), cada "operação" é
uma instrução nativa. Em hardware moderno, isso executa em ~1-5ms — abaixo
do limiar de percepção humana.

### 4.2 A Otimização por Score Cutoff

O rapidfuzz implementa **early exit** quando um score cutoff é fornecido.
Para Levenshtein, é possível determinar o score máximo possível apenas
comparando os comprimentos das strings:

```
score_max = 1 - |len(s1) - len(s2)| / max(len(s1), len(s2))
```

Se `score_max < threshold`, a comparação é descartada sem computar o
alinhamento completo. Para um threshold de 0.85, qualquer par de strings
com diferença de comprimento > 15% do máximo é descartado imediatamente.

Com o vocabulário do Total Recall (distribuição de comprimento 1–34 chars,
média 7.1), isso elimina tipicamente 60–70% das comparações antes de
começar o cálculo de distância.

### 4.3 O Problema do Cache de Vocabulário

Uma implementação ingênua consultaria o FTS5 para extrair o vocabulário a
cada busca. A query:

```sql
SELECT term FROM chunks_fts_data WHERE col = 'content'
```

Sobre 596 chunks com ~5.672 termos únicos: ~2-5ms de I/O. Multiplique por
todas as buscas da sessão. O cache com TTL de 60s proposto no plano V2
reduz isso para zero em condições normais.

---

## 5. O Problema Específico do Vocabulário Técnico

Esta seção é o coração do problema. O corpus do Total Recall não é um corpus
de linguagem natural — é um corpus técnico híbrido (pt-BR + inglês) composto
predominantemente de:

1. **Nomes de bibliotecas e ferramentas**: `sqlite-vec`, `qwen3-embedding`,
   `chromadb`, `rapidfuzz`, `spellfix1`
2. **Identificadores de código**: `session_id`, `chunk_index`, `embed_model`,
   `file_hash`
3. **Nomes de projetos e conceitos**: `memoria-viva`, `total-recall`,
   `pgvector`
4. **Termos técnicos específicos do domínio**: `WAL`, `FTS5`, `BM25`, `MMR`,
   `cosine similarity`

Este perfil de vocabulário invalida as soluções "padrão" para spell-checking:

### 5.1 Por que Hunspell/aspell Falham

Hunspell e aspell são construídos sobre dicionários de linguagem natural e
regras morfológicas. `sqlite` não está no dicionário. `qwen3` não está. O
corretor retornaria `"salite"`, `"suite"`, `"alike"` — todas erradas.

### 5.2 Por que Algoritmos Fonéticos Falham

Soundex, Metaphone e Double Metaphone codificam a **pronúncia aproximada**
de palavras em inglês. `sqlite` → `S430`, `sqilte` → `S430` (pode funcionar
por acidente). Mas `qwen3` → `QN3`, e `qwen` não tem codificação fonética
confiável em inglês. Para qualquer identificador com dígitos ou com prefixos
técnicos, os algoritmos fonéticos produzem resultados não-determinísticos.

### 5.3 A Vantagem do Corpus-Anchored Vocabulary

A solução do rapidfuzz no contexto do Total Recall tem uma propriedade que
a torna superior a spell-checkers genéricos: ela usa o **vocabulário real do
corpus indexado** como referência.

Se o usuário digita `qwen3-embeding`, o sistema não tenta corrigir baseado
em inglês geral — ele compara contra os termos que **realmente aparecem** nas
sessões indexadas. Se `qwen3-embedding` aparece 47 vezes no índice, ele está
no vocabulário. A correção é ancorada na realidade do corpus.

Esta é a distinção fundamental entre:
- **Spell-checking genérico**: corrige para o dicionário da língua
- **Approximate vocabulary matching**: corrige para o vocabulário do índice

Para um sistema de recuperação, a segunda abordagem é sempre superior.

---

## 6. A Expansão de Query — Arquitetura Formal

O mecanismo proposto é uma forma de **Query Expansion via Approximate
Vocabulary Matching**. Formalizando:

```
Seja V = {t₁, t₂, ..., tₙ} o vocabulário do índice FTS5
Seja Q = {q₁, q₂, ..., qₘ} os tokens da query do usuário
Seja sim(a, b) uma função de similaridade normalizada em [0,1]
Seja θ o threshold (default 0.85)

Para cada token qᵢ ∈ Q:
  Sᵢ = { t ∈ V : sim(qᵢ, t) ≥ θ } ∪ {qᵢ}   (candidatos similares)
  Sᵢ = top_k(Sᵢ, k=FUZZY_MAX_EXPANSIONS)     (limitar expansão)

Query expandida:
  Q' = (q₁ OR s₁.₁ OR s₁.₂) (q₂ OR s₂.₁) ... (qₘ OR sₘ.₁)
```

A query expandida é passada ao FTS5 que aplica BM25 sobre cada combinação
possível. O FTS5 avalia a query como:

```sql
SELECT rowid, rank
FROM chunks_fts
WHERE chunks_fts MATCH '("sqilte" OR "sqlite") ("vec")'
ORDER BY rank;
```

O resultado é um merge de todos os documentos que contêm qualquer variante
de cada grupo, rankeados pelo BM25 da melhor combinação encontrada.

### 6.1 Interação com o Sistema Híbrido

No Total Recall, a busca keyword é apenas 30% do score final. O pipeline
completo após a expansão fuzzy:

```
Query expandida
    │
    ├─ FTS5 BM25 (30%)     ← expansão fuzzy melhora este componente
    │   → ranked_fts_results
    │
    ├─ Vector similarity (70%)   ← não muda; usa a query original
    │   → ranked_vec_results
    │
    ▼
Normalized score combination:
  score = 0.7 × vec_score + 0.3 × fts_score
    │
    ▼
Temporal decay × role weights
    │
    ▼
MMR re-ranking
    │
    ▼
Top-5 results
```

A expansão fuzzy atua exclusivamente no componente FTS5. O componente vetorial
não é afetado — e não deveria ser, porque embeddings de tokens com typos já
são tão imprecisos que não há ganho em expandi-los.

---

## 7. Calibração do Threshold — A Decisão Mais Crítica

O threshold θ é o único hiperparâmetro crítico da solução. A curva de
custo-benefício é assimétrica:

```
         Falsos positivos (ruído nos resultados)
              ▲
              │
         Alta │ ─────────────────────────────────────╮
              │                                      │ threshold muito baixo
         Baixa│                              ╭───────╯
              │                      ╭───────╯
              │              ╭───────╯
           0  └──────────────┴─────────────────────────────→
              0.6         0.75      0.85       0.95    1.0
                                     ↑
                              Default proposto
```

```
         Casos cobertos (typos corrigidos)
              ▲
         Alta │ ╭─────────────────────────────────────
              │ │
         Baixa│ │                              ╭───────
              │ │                      ╭───────╯
              │ │              ╭───────╯
           0  └─┴──────────────┴─────────────────────────────→
              0.6         0.75      0.85       0.95    1.0
```

Para o vocabulário técnico do Total Recall, a calibração recomendada
segue o seguinte raciocínio:

**Threshold 0.85** cobre:
- Strings com comprimento ≥ 7: 1 substituição ou 1 transposição
- Strings com comprimento ≥ 10: até 1.5 operações (1 sub + 1 ins)
- NÃO cobre: strings curtas (≤ 5 chars) com 1 substituição — como `novax→novex`

**Threshold 0.80** cobre adicionalmente:
- Strings com comprimento ≥ 5: 1 substituição
- Aumenta falsos positivos para tokens genéricos curtos

**Recomendação**: manter 0.85 e compensar strings curtas com o motor vetorial,
que para nomes de projetos com contexto rico tende a funcionar bem.

---

## 8. Alternativa — Reescrita de Query por LLM

O Total Recall opera dentro do Claude Code via a skill `/recall`. Isso significa
que há um LLM no loop — especificamente Claude, com capacidade sofisticada de
processamento de linguagem natural e conhecimento técnico.

A alternativa ao fuzzy matching em Python é usar o LLM para **reescrita de
query** antes de passar ao motor de busca. Esta abordagem é chamada na
literatura de **Query Rewriting** ou **HyDE** (Hypothetical Document
Embeddings na variante para RAG).

### 8.1 Como Funciona

Modificação exclusiva em `skill/recall.md` — zero mudança no código Python:

```markdown
# skill/recall.md (modificado para query rewriting)

Antes de executar a busca:
1. Analise a query do usuário. Se suspeitar de typos em nomes técnicos
   (bibliotecas, projetos, identificadores), gere variantes corrigidas.
2. Execute a busca com a query original E com as variantes.
3. Combine e desduplique os resultados.

Exemplo:
  Query: "sqilte vec"
  → Detecta typo: "sqilte" → provável "sqlite"
  → Executa: total-recall search "sqlite vec" --format context --limit 8
  → Se sem resultados: total-recall search "sqilte vec" --format context --limit 8
```

### 8.2 Vantagens sobre rapidfuzz

| Dimensão | rapidfuzz | LLM Query Rewriting |
|---|---|---|
| Mudanças de código | `vector_store.py` + `config.py` | Só `skill/recall.md` |
| Conhecimento técnico | Limitado ao corpus | Conhecimento global de tecnologias |
| Handles neologismos | Não (não está no vocabulário) | Sim |
| Determinismo | Sim | Não |
| Funciona via CLI | Sim | Não (só via `/recall`) |
| Funciona offline (sem Claude) | Sim | Não |
| Latência | +50-100ms | +Claude inference time |
| Cobertura cross-lingual | Via corpus vocab | Nativa |

### 8.3 Limitações da Abordagem LLM

**Não determinismo**: a mesma query pode produzir resultados diferentes entre
execuções. Para um sistema de recuperação, isso é problemático em depuração.

**Dependência de contexto**: o LLM não tem acesso direto ao vocabulário do
índice — pode gerar variantes que não existem no corpus. `rapidfuzz` está
ancorado no vocabulário real; o LLM está ancorado no conhecimento geral.

**Disponibilidade**: via CLI (`total-recall search` diretamente no terminal),
não há LLM no loop. A expansão fuzzy precisaria estar no código Python.

**Latência de API**: mesmo com Claude local (Ollama), a inferência para
reescrita de query adiciona 500ms-2s, dependendo do hardware.

### 8.4 Como o OpenClaw Resolve Isso

O OpenClaw posiciona o LLM como participante ativo na pipeline de retrieval,
não apenas na apresentação dos resultados. Na arquitetura documentada, o LLM:

1. **Analisa a intent da query** — não apenas keywords, mas o que o usuário
   realmente quer recuperar
2. **Reformula a query** — expande com termos relacionados, corrige prováveis
   erros, adiciona contexto temporal
3. **Valida os resultados** — filtra resultados recuperados que não são
   realmente relevantes antes de apresentar ao usuário

Esta abordagem é chamada na literatura de **LLM-as-Retriever** — onde o modelo
de linguagem participa ativamente na decisão de relevância, não apenas na
geração da resposta final.

O ponto central: o OpenClaw **não resolve typo tolerance com código** — resolve
com a capacidade do LLM de entender intenção e reformular. Para um sistema
onde o LLM está sempre disponível, isso é elegante. Para um sistema que precisa
funcionar sem LLM (modo offline, CLI puro, automações), não é suficiente.

### 8.5 A Recomendação: Abordagem em Camadas

As duas abordagens não são mutuamente exclusivas. A arquitetura ideal é:

```
/recall <query>
    │
    ├─ [LLM Claude] Analisa query, detecta typos óbvios,
    │   reformula se necessário
    │
    ▼
total-recall search "<query reformulada>" --format context
    │
    ├─ [Python] _expand_abbreviations() — V1
    ├─ [Python] _expand_fuzzy()          — V2, se rapidfuzz instalado
    ├─ [Python] Vector search (70%)
    └─ [Python] FTS5 keyword (30%)
```

LLM cuida dos casos semânticos complexos (intenção, contexto, knowledge geral).
rapidfuzz cuida dos casos mecânicos determinísticos (1-2 caracteres de diferença
contra o vocabulário real do índice).

---

## 9. O Caso Especial dos Identificadores Técnicos

Uma análise dos 5.672 termos únicos no vocabulário FTS5 do Total Recall
revela que aproximadamente 30-40% são identificadores técnicos não-dicionário:
nomes de bibliotecas, variáveis, UUIDs parciais, versões. Estes são o pior
caso para qualquer approach de spell-checking.

Para esses casos, a hierarquia de efetividade das abordagens é:

```
1. Vocabulário do corpus (rapidfuzz ancorado no FTS5)   — mais preciso
2. LLM com conhecimento técnico global                  — mais abrangente
3. Embedding vetorial com contexto rico                 — fallback para nomes comuns
4. Spell-checker genérico (Hunspell)                    — pior, frequentemente errado
```

A sequência 1 → 3 representa exatamente a pipeline do Total Recall após a
implementação da V2. O spell-checker genérico nunca deve ser considerado
para este perfil de corpus.

---

## 10. Sumário Técnico

| Componente | O que resolve | Mecanismo |
|---|---|---|
| FTS5 unicode61 | `você` = `voce` = `vocé` | Remoção de diacríticos na tokenização |
| V1 `_PT_ABBREVIATIONS` | `vc` → `você` | Expansão OR-groups antes do FTS5 |
| V2 `rapidfuzz` | `sqilte` → `sqlite` | Levenshtein contra vocabulário do índice |
| qwen3-embedding:4b | Paráfrases, sinônimos, cross-lingual | Similaridade cosine no espaço vetorial |
| LLM Query Rewriting | Intenção, contexto, conhecimento geral | Inferência LLM na skill /recall |

Nenhuma solução individual cobre todos os casos. O Total Recall, na sua
arquitetura atual (mais V1 e V2), cobre os quatro quadrantes do problema
de vocabulary mismatch que são relevantes para seu perfil de corpus.

---

## Referências e Leituras Complementares

As referências estão organizadas por tema. Para cada área, a ordem sugere
uma progressão de leitura — do fundacional ao aplicado.

---

### Fundamentos de Recuperação de Informação

**O livro de referência da área** — disponível gratuitamente online:

- **Manning, C.D., Raghavan, P., Schütze, H.** (2008). *Introduction to
  Information Retrieval*. Cambridge University Press.
  https://nlp.stanford.edu/IR-book/
  *(Capítulos 1–3 para IR clássico; cap. 6 para scoring e BM25;
  cap. 19 para web search e expansão de query)*

- **Büttcher, S., Clarke, C., Cormack, G.V.** (2010). *Information Retrieval:
  Implementing and Evaluating Search Engines*. MIT Press.
  *(Mais prático que Manning et al.; cobre implementação de índice invertido,
  BM25 e avaliação de sistemas)*

---

### BM25 e Modelos Probabilísticos de Relevância

- **Robertson, S.E., Walker, S., Jones, S., Hancock-Beaulieu, M., Gatford, M.**
  (1994). Okapi at TREC-3. *NIST Special Publication 500-225*, 109–126.
  *(O paper onde BM25 aparece pela primeira vez com esse nome)*

- **Robertson, S., Zaragoza, H.** (2009). The probabilistic relevance
  framework: BM25 and beyond. *Foundations and Trends in Information
  Retrieval*, 3(4), 333–389.
  *(A referência definitiva de BM25; cobre as variantes BM25F para campos
  múltiplos — relevante para entender como o FTS5 aplica o ranking)*

- **Sparck Jones, K., Walker, S., Robertson, S.E.** (2000). A probabilistic
  model of information retrieval: development and comparative experiments.
  *Information Processing & Management*, 36(6), 779–840.
  *(Fundações teóricas do modelo probabilístico de relevância — leitura
  densa mas essencial para entender por que BM25 funciona)*

---

### Distância de Edição e Approximate String Matching

**Leitura fundamental** — um dos melhores surveys já escritos sobre o tema:

- **Navarro, G.** (2001). A guided tour to approximate string matching.
  *ACM Computing Surveys*, 33(1), 31–88.
  https://dl.acm.org/doi/10.1145/375360.375365
  *(Cobre Levenshtein, Damerau, Hamming, LCS, algoritmos de busca com
  autômatos, bitmask tricks — o guia completo)*

Os papers originais das métricas:

- **Wagner, R.A., Fischer, M.J.** (1974). The string-to-string correction
  problem. *Journal of the ACM*, 21(1), 168–173.
  *(Formulação do algoritmo dinâmico para Levenshtein — mais rigoroso que
  o paper do próprio Levenshtein)*

- **Levenshtein, V.I.** (1966). Binary codes capable of correcting deletions,
  insertions, and reversals. *Soviet Physics Doklady*, 10(8), 707–710.
  *(O paper original — curto, denso, impactante)*

- **Damerau, F.J.** (1964). A technique for computer detection and correction
  of spelling errors. *Communications of the ACM*, 7(3), 171–176.
  *(Adiciona transposição ao Levenshtein — fundamental para erros de digitação
  reais, onde "il" → "li" é o erro mais comum)*

- **Ukkonen, E.** (1985). Algorithms for approximate string matching.
  *Information and Control*, 64(1–3), 100–118.
  *(Algoritmo O(kn) para Levenshtein com cutoff k — base dos algoritmos
  modernos de early-exit, como o usado pelo rapidfuzz)*

- **Myers, G.** (1999). A fast bit-vector algorithm for approximate string
  matching based on dynamic programming. *Journal of the ACM*, 46(3), 395–415.
  *(O algoritmo "bit-parallel" que os sistemas de alto desempenho usam —
  incluindo o rapidfuzz em C++)*

---

### Query Expansion

- **Carpineto, C., Romano, G.** (2012). A survey of automatic query expansion
  in information retrieval. *ACM Computing Surveys*, 44(1), 1–50.
  *(O survey mais completo de query expansion — cobre pseudo-relevance
  feedback, thesaurus-based expansion, e expansion via co-occurrence)*

- **Berger, A., Lafferty, J.** (1999). Information retrieval as statistical
  translation. *SIGIR '99*, 222–229.
  *(Paper seminal que modela IR como problema de tradução automática —
  base teórica para expansão de query via modelo de linguagem)*

- **Voorhees, E.M.** (1994). Query expansion using lexical-semantic relations.
  *SIGIR '94*, 61–69.
  *(Expansão via WordNet — relevante como contraste: mostra por que
  expansão ancorada no corpus (como a nossa) funciona melhor que expansão
  via ontologia genérica para domínios técnicos)*

---

### Dense Retrieval e Sistemas Híbridos

- **Karpukhin, V. et al.** (2020). Dense passage retrieval for open-domain
  question answering. *EMNLP 2020*, 6769–6781.
  https://arxiv.org/abs/2004.04906
  *(DPR — o paper que estabeleceu dense retrieval como paradigma dominante;
  contexto essencial para entender por que sistemas híbridos existem)*

- **Zhao, W. et al.** (2024). Dense text retrieval based on pretrained language
  models: A survey. *ACM Transactions on Information Systems*, 42(4).
  https://arxiv.org/abs/2211.14876
  *(Survey completo do estado da arte em dense retrieval — cobre o vocabulary
  mismatch problem no contexto de embeddings)*

- **Chen, J. et al.** (2022). ECIR 2022: Salient phrase aware dense retrieval.
  *(Como sistemas híbridos tratam entidades nomeadas e identificadores técnicos
  — exatamente o problema que temos com nomes de bibliotecas)*

---

### LLM como Query Rewriter (abordagem alternativa ao fuzzy)

- **Gao, L. et al.** (2022). Precise zero-shot dense retrieval without
  relevance labels. *arXiv:2212.10496*.
  https://arxiv.org/abs/2212.10496
  *(HyDE — Hypothetical Document Embeddings. Usa LLM para gerar um documento
  hipotético que responderia a query, e embeda esse documento. Metodologia
  elegante para quando o query e os documentos têm distribuições diferentes)*

- **Wang, L. et al.** (2023). Query2Doc: Query expansion with large language
  models. *EMNLP 2023*.
  https://arxiv.org/abs/2303.07678
  *(LLM gera um "pseudo-documento" que serve de expansão de query —
  parente próximo do HyDE; fundamenta a abordagem LLM Query Rewriting)*

- **Ma, X. et al.** (2023). Query rewriting for retrieval-augmented large
  language models. *EMNLP 2023*.
  https://arxiv.org/abs/2305.14283
  *(Reescrita explícita de query pelo LLM em pipelines RAG — o caso de uso
  mais próximo do que propomos com a skill /recall)*

- **Jagerman, R., Zhuang, H., Qin, Z., Wang, X., Bendersky, M.** (2023).
  Query expansion by prompting large language models.
  *arXiv:2305.03653*.
  https://arxiv.org/abs/2305.03653
  *(Avaliação sistemática de LLM para query expansion — inclui análise de
  quando funciona bem e quando falha; útil para calibrar expectativas)*

---

### Modelos de Embedding Multilíngues

- **Team Qwen.** (2025). Qwen3 Embedding: Advancing Text Embedding and
  Reranking through Foundation Models. *arXiv*.
  https://arxiv.org/abs/2506.05176
  *(Technical report do qwen3-embedding — nosso modelo atual. Seção 3
  sobre instruction-aware embeddings é especialmente relevante)*

- **Nussbaum, Z. et al.** (2024). Nomic Embed: Training a reproducible long
  context text embedder. *arXiv:2402.01613*.
  https://arxiv.org/abs/2402.01613
  *(Technical report do nomic-embed-text — nosso modelo anterior.
  Útil como baseline de comparação para entender o ganho do Qwen3)*

- **Muennighoff, N. et al.** (2022). MTEB: Massive Text Embedding Benchmark.
  *EACL 2023*. https://arxiv.org/abs/2210.07316
  *(O benchmark que usamos para comparar modelos — entender como os scores
  são calculados é essencial para interpretar os 69.45 do Qwen3 vs ~60 do nomic)*

---

### SymSpell — A Alternativa ao rapidfuzz não Mencionada no Plano V2

Um algoritmo que merece estudo independente: o **SymSpell**, desenvolvido
por Wolf Garbe. Não há paper formal, mas a publicação técnica é rigorosa:

- **Garbe, W.** (2012, atualizado 2019). *1000x faster spelling correction
  algorithm*. Publicação técnica.
  https://wolfgarbe.medium.com/1000x-faster-spelling-correction-algorithm-using-symmetric-delete-spelling-correction-e8f7a28e2952

  **Por que é relevante**: o SymSpell inverte o problema. Em vez de computar
  distância de edição *da query para o vocabulário*, ele pré-computa todas as
  palavras que estão a distância 1 e 2 do vocabulário por deleção, as armazena
  num hash. Na busca, deleta caracteres da query e intersecciona com o hash.
  Resultado: O(1) de lookup vs O(n×L²) do Levenshtein ingênuo.

  Para vocabulários grandes e buscas frequentes, SymSpell é mais eficiente que
  rapidfuzz. Para vocabulários pequenos (~5k tokens como o nosso) e buscas
  ocasionais, o overhead de pré-computação não se justifica.

  **Implementação Python**: `pip install symspellpy` (inclui suporte a
  dicionários customizados — relevante para carregarmos o vocabulário FTS5).

---

### Inverted Index e FTS em Profundidade

- **Zobel, J., Moffat, A.** (2006). Inverted files for text search engines.
  *ACM Computing Surveys*, 38(2), article 6.
  *(Referência fundamental para entender como o índice invertido do FTS5
  funciona internamente — desde estruturas de dados até query processing)*

- **SQLite FTS5 documentation** (2023). SQLite.org.
  https://www.sqlite.org/fts5.html
  *(A documentação oficial do FTS5 é excepcionalmente bem escrita —
  especialmente as seções sobre tokenizers, BM25 implementation e
  auxiliary functions como fts5vocab)*

---

### RAG (Retrieval-Augmented Generation) — Contexto Mais Amplo

- **Lewis, P. et al.** (2020). Retrieval-augmented generation for
  knowledge-intensive NLP tasks. *NeurIPS 2020*.
  https://arxiv.org/abs/2005.11401
  *(O paper RAG original da Meta — contextualiza o Total Recall dentro
  do paradigma mais amplo de sistemas de memória aumentada)*

- **Gao, Y. et al.** (2023). Retrieval-augmented generation for large
  language models: A survey. *arXiv:2312.10997*.
  https://arxiv.org/abs/2312.10997
  *(Survey abrangente de RAG — cobre retrieval quality, query processing,
  e avaliação de sistemas; seção 4 é especialmente relevante para nós)*
