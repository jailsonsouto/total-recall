# GANCHO DE SESSÃO — Meilisearch × Total Recall

**Data**: 2026-04-14  
**Status**: PAUSADO — exploração em andamento

---

## O que estava sendo feito

Exploração conceitual de features do **Meilisearch** (https://github.com/meilisearch/meilisearch) para avaliar o que poderia ser incorporado/inspirar o mecanismo de busca do **Total Recall**.

Perfil pedido: Engenheiro de Dados especialista em LLM, NLP, ABSA, Vector DB e lógica Fuzzy.

O resultado final deve ser salvo como markdown de análise nesta mesma pasta (`docs/`).

---

## O que já foi feito

### ✅ Exploração do Total Recall (concluída)

O mecanismo de busca atual foi mapeado completamente. Principais achados:

| Componente | Detalhes |
|---|---|
| Busca semântica | sqlite-vec + qwen3-embedding:4b (1024 dims, instruction-aware) |
| Busca lexical | FTS5 + BM25 + normalização PT-BR + fuzzy via rapidfuzz |
| Fusão | Ponderação adaptativa (70/30 híbrida ou 25/75 FTS-dominante) |
| Piso de confiança | MIN_VECTOR_ONLY_SCORE = 0.42 (workaround assimetria de scores) |
| Pós-processamento | Temporal decay exponencial (meia-vida 30 dias) + MMR re-ranking |
| Arquivos-chave | vector_store.py, recall_engine.py, database.py, session_parser.py, config.py |

**Limitações identificadas** (APRENDIZADOS.md, itens 24–42):
- MMR usa Jaccard em vez de cosine para chunks FTS-only
- Queries mistas (stop words + termos técnicos) têm pesos binários, não proporcionais
- Threshold fuzzy absoluto (doc_count ≤ 10) degrada com crescimento do corpus
- Timestamp de chunk = timestamp de sessão inteira (decay impreciso)
- Overlap de chunking cria duplicatas no FTS5

### ❌ Exploração do Meilisearch (NÃO concluída)

O agent foi interrompido antes de retornar. Precisa ser refeito.

---

## Próximos passos ao retomar

1. **Relançar agent Explore** para pesquisar Meilisearch:
   - Busca híbrida (vector + full-text, `semanticRatio`)
   - Typo tolerance / Fuzzy (Levenshtein, `minWordSizeForTypos`)
   - Ranking rules customizáveis
   - Facets e filtros de metadados
   - Phrase search, operadores AND/OR/NOT
   - Highlighting de snippets
   - Arquitetura interna (LMDB? RocksDB?)
   - Limitações do Meilisearch

2. **Consolidar análise comparativa** em:
   - O que o Meilisearch faz melhor que o estado atual do Total Recall
   - O que pode ser portado como conceito (sem adotar Meilisearch como dependência)
   - O que não se aplica ao contexto SQLite-local

3. **Salvar resultado final em** `docs/ANALISE_MEILISEARCH_TOTAL_RECALL_2026-04-14.md`

---

## Como retomar

Diga ao Claude: **"retoma o gancho do Meilisearch"** e aponte para este arquivo.
