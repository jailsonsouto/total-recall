# De Memória a Conhecimento — Perspectiva Arquitetônica sobre RAG Híbrido

> Documento de referência para uso futuro. Gerado a partir de análise prática
> do Total Recall e das implicações do desequilíbrio FTS5/vetor descoberto em 2026-03-26.

---

## Contexto de origem

Durante o desenvolvimento do Total Recall (ferramenta de memória para sessões do Claude Code CLI),
uma busca por `"netnografia"` revelou um problema estrutural: resultados de ruído vetorial
(score 0.38–0.41, vector-only) mascaravam resultados FTS5 genuínos (score 0.08–0.09) que
continham a palavra literal no corpus.

A análise desse incidente levantou questões mais amplas sobre a diferença arquitetônica entre
sistemas de memória conversacional e bases de conhecimento organizacionais.

---

## O que o Total Recall é, arquitetonicamente

O Total Recall implementa um **RAG híbrido de memória conversacional**. O pipeline é idêntico
ao de qualquer RAG de base de conhecimento:

```
Corpus (JSONLs) → Chunking → Embedding → Índice vetorial + BM25
      Query → Embedding → Busca híbrida → Re-ranking → Resposta aumentada
```

A diferença não é arquitetônica — é de **natureza do corpus** e **intenção de uso**.

---

## Tabela comparativa

| Dimensão | Total Recall (memória) | RAG de base de conhecimento |
|---|---|---|
| **Corpus** | Conversas — fluido, pessoal, imperfeito | Documentos — PDFs, wikis, manuais estruturados |
| **Autoria** | Um usuário + Claude | Especialistas, equipes, fontes externas |
| **Temporalidade** | Cresce continuamente, data é relevante | Relativamente estático, versões controladas |
| **Unidade semântica** | Exchange (pergunta + resposta) | Parágrafo, seção, documento |
| **Query típica** | "Por que decidimos X?" | "Como funciona X?" |
| **Intenção** | Recuperar o que foi *pensado* | Recuperar o que é *verdadeiro* |
| **Controle de versão** | Append-only por design (JSONLs) | Versionamento explícito necessário |
| **Temporal decay** | Necessário (recência importa) | Geralmente desnecessário |
| **Autoria múltipla** | Não | Necessário (controle de acesso) |

---

## O desequilíbrio FTS5/vetor — problema mais crítico em bases de conhecimento

O problema descoberto no Total Recall seria ainda mais severo numa base de conhecimento técnica.
O corpus teria siglas, nomes de produtos e termos de domínio — todos raros, encontráveis apenas
via FTS5 literal. O padrão "ruído vetorial mascara match FTS5 real" seria a norma, não a exceção.

```
Score máximo puro FTS5:   TEXT_WEIGHT × 1.0 = 0.30
Ruído vetorial típico:    0.38–0.41
→ FTS5 genuíno perde para vetor ruído sistematicamente
```

**Causa raiz**: a ponderação 70/30 foi desenhada assumindo que queries são primariamente semânticas.
Para termos técnicos/raros/próprios, a premissa inverte — FTS5 é o sinal primário, vetor é ruído.

### A solução arquitetônica correta: ponderação adaptativa

```
Query classificada como específica/técnica/rara:
  → Modo FTS5-dominante (ex: 20% vetor / 80% FTS5)

Query classificada como semântica/difusa/conceitual:
  → Modo híbrido padrão (70% / 30%)

Sinais de classificação:
  - doc_count no vocabulário FTS5 (raro → técnico → FTS5-dominant)
  - Morfologia do termo (maiúsculas, acrônimos, neologismos)
  - Presença de match FTS5 vs ausência (o resultado em si informa o modo)
```

Alternativa mais robusta: normalizar os scores de cada modalidade *dentro da sua própria
distribuição* antes de combinar, em vez de usar pesos absolutos. Se o melhor score vetorial
é 0.41 e o melhor FTS5 é 0.09, eles são "igualmente bons" em termos relativos.

---

## O que um RAG de base de conhecimento adiciona

### 1. Reranking com cross-encoder
Um segundo modelo (menor, mais preciso) que recebe pares (query, chunk) e reordena os candidatos.
O hybrid_search + MMR que o Total Recall usa é um reranker heurístico; o cross-encoder aprende
o que é relevante do contexto completo do par. Melhora recall com overhead moderado.

### 2. Metadata filtering antes da busca
Filtrar por tipo de documento, data de publicação, departamento, autor, tag antes de buscar.
O `--session` do Total Recall é a versão simplificada disso.

### 3. Chunking com hierarquia
Indexar em múltiplos níveis (frase, parágrafo, seção, documento) e usar o nível certo
dependendo da query. Queries específicas → chunks pequenos. Queries conceituais → chunks grandes.
O Total Recall usa exchange-based chunking, que é uma hierarquia implícita de dois níveis
(exchange completo + subdivisão com overlap).

### 4. Atualização incremental controlada com invalidação
Documentos de conhecimento têm versões. Um PDF novo pode invalidar chunks antigos de forma
não-trivial. O append-only do Total Recall funciona porque JSONLs do Claude Code são cumulativos
por design — documentos de conhecimento não são.

### 5. Acesso diferenciado e governança
Múltiplos consumidores com permissões diferentes sobre o mesmo corpus. O Total Recall é single-user
por design — toda a complexidade de governança não existe.

---

## O que é reaproveitável diretamente

A infraestrutura do Total Recall (SQLite WAL + sqlite-vec + FTS5 + Qwen3 + rapidfuzz) é
reutilizável sem modificação de arquitetura para:

- Documentos Markdown (notas, pesquisas, journaling)
- Transcrições de reuniões e entrevistas
- Corpus bilíngue de qualquer natureza
- Base de conhecimento pessoal de pequena/média escala

**O que precisaria ser adaptado:**
- Chunking: exchange-based → por parágrafo/seção com overlap configurável
- Temporal decay: seria desativado ou muito suavizado (documentos não envelhecem igual a conversas)
- Indexação seletiva de blocos internos: não existiria (documentos não têm `thinking`)
- Ponderação adaptativa: se tornaria obrigatória (não opcional como no Total Recall)

---

## A pergunta de fundo

O que separa uma ferramenta de memória pessoal de uma base de conhecimento organizacional?

**Arquitetonicamente: muito pouco.** O pipeline vetorial + BM25 + re-ranking é o mesmo.

O que muda é política: quem indexa o quê, com que granularidade, com que controle de versão,
com que garantia de frescor, e com que controle de acesso.

O Total Recall resolve o problema mais simples: um corpus homogêneo, de um autor, com uma
fonte de verdade (os JSONLs). Um sistema de conhecimento organizacional resolve o problema
mais difícil: múltiplos autores, múltiplos formatos, múltiplas versões, múltiplos consumidores
com acesso diferenciado.

**A infraestrutura para o primeiro leva ao segundo. O que falta não é tecnologia — é governança.**

---

## FTS5 como prova de existência — princípio geral

A descoberta mais transferível deste trabalho:

> *Se FTS5 encontrou o termo, ele literalmente existe no corpus. É um sinal duro, binário,
> confiável. Resultado FTS5 = existência confirmada. Resultado VECTOR = inferência probabilística.*

Em qualquer sistema RAG, um match literal via índice invertido (BM25/FTS5) deveria ter garantia
de visibilidade — não pode ser sistematicamente derrotado por inferência vetorial de baixa qualidade.
Isso não significa que FTS5 sempre vença; significa que sua existência nunca deve ser silenciada
por ruído.

Implementação prática: score mínimo para resultados vector-only + passagem incondicional para
resultados com contribuição FTS5. Ver `vector_store.py:hybrid_search()` no Total Recall para
referência de implementação.

---

## Stack de referência (Total Recall, 2026-03-26)

| Componente | Versão/Config | Papel |
|---|---|---|
| SQLite WAL | built-in | Banco único, crash-safe |
| sqlite-vec | virtual table | Busca vetorial cosine similarity |
| FTS5 + fts5vocab | built-in | BM25 + vocabulário para fuzzy |
| qwen3-embedding:4b | 1024 dims | Embeddings multilíngues instruction-aware |
| rapidfuzz | ≥3.0 | Fuzzy matching C++, 0.2ms/token |
| Ollama | local | Runtime para embedding |

*Para detalhes de implementação, ver `src/total_recall/vector_store.py` e `recall_engine.py`.*

---

*Gerado em 2026-03-26 a partir de análise do Total Recall V02.3.*
*Projeto de origem: `agentes/projetos/total-recall`*
