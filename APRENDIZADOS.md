# APRENDIZADOS — Total Recall

> Documento vivo. Atualizar sempre que um aprendizado significativo surgir.

## 2026-03-24 — Início do projeto

1. **JSONL do Claude Code tem estrutura rica**
   - Tipos: system, user, assistant, progress, file-history-snapshot, custom-title, agent-name
   - Mensagens assistant têm content como array de blocos (text, thinking, tool_use, tool_result)
   - Mensagens user têm content como string simples
   - `isSidechain: true` marca mensagens de subagentes no stream principal
   - `parentUuid` permite reconstruir a árvore de conversa

2. **Exchange-based chunking é superior a per-message**
   - Pergunta + resposta formam uma unidade semântica
   - Indexar separado perde o contexto da pergunta na resposta

3. **Padrões copiados do Memória Viva funcionam direto**
   - Database class com WAL + sqlite-vec → robusto
   - VectorStore com hybrid search → 70% vetor + 30% FTS5
   - EmbeddingProvider abstrato → troca sem dor

## 2026-03-24 — Indexação seletiva (Option 3) + bugfix session prefix

4. **Thinking/tool_result contêm informação valiosa que era perdida**
   - O parser original só indexava blocos `text` (resposta visível)
   - Blocos `thinking` têm raciocínio do Claude: intenção do usuário, diagnósticos, planos
   - Blocos `tool_result` têm contexto técnico: schemas, ADRs, outputs de ferramentas
   - Sem indexá-los, buscas como "renomear pasta projetos/novex" falhavam porque o conteúdo só existia no thinking
   - **Onde**: `session_parser.py:20-46` (_SELECTIVE_MARKERS + funções de extração)

5. **Indexação seletiva com marcadores é o equilíbrio certo**
   - Indexar TODO thinking/tool_result gera ruído excessivo (logs de ferramentas, tentativas descartadas)
   - Indexar NADA perde decisões e diagnósticos cruciais
   - Option 3: indexar apenas quando contém palavras-chave de decisão/intenção/diagnóstico
   - Marcadores em português E inglês (ex: "decisão", "ADR", "root cause", "o usuário quer")
   - Role weights reduzem prioridade: thinking=0.6, tool_context=0.7 (vs exchange=1.0)
   - **Onde**: `recall_engine.py:66-75` (role weights), `session_parser.py:345-372` (passada 2)

6. **Bug do prefixo de session_id: comparação exata mata filtro**
   - CLI recebe `--session 9739fab2` (prefixo de 8 chars)
   - Banco armazena UUID completo: `9739fab2-3f37-45de-ac1f-913b54f988c5`
   - `keyword_search()` e `search()` faziam `meta["session_id"] != session_id` → sempre True
   - Resultado: filtro de sessão descartava TODOS os resultados silenciosamente
   - Fix: `_resolve_session_id()` faz LIKE no banco antes da busca híbrida
   - **Onde**: `recall_engine.py:93-104` (_resolve_session_id)

7. **FTS5 lida bem com "/" nos termos de busca**
   - Tokenizador unicode61 (default) trata "/" como separador
   - "projetos/novex" vira tokens ["projetos", "novex"] tanto no índice quanto na query
   - Busca por frase `"projetos/novex"` encontra adjacência corretamente
   - Não foi necessário sanitizar "/" na query

8. **Chunks sem embedding (has_embedding=0) ainda são buscáveis via FTS5**
   - Quando Ollama gera embedding, chunk aparece na busca vetorial E keyword
   - Quando não gera (erro, indisponível), chunk só aparece na keyword (FTS5)
   - A busca híbrida combina ambas, então chunks FTS-only ainda aparecem nos resultados
   - Isso é o graceful degradation funcionando como desenhado

## 2026-03-24 — Migração para qwen3-embedding:4b

9. **qwen3-embedding:4b é muito superior ao nomic-embed-text para este caso**
   - Score MTEB multilingual: 69.45 (qwen3-4b) vs ~60 (nomic)
   - Cross-lingual funciona: query em inglês encontra conteúdo em pt-BR e vice-versa
   - Instruction-aware: queries recebem instrução, documentos não — melhora recall
   - Teste real: "renomear pasta projetos/novex" subiu de score 0.066 → 0.528 no resultado correto
   - **Onde**: `embeddings.py` (OllamaEmbedProvider), `config.py` (OLLAMA_EMBED_MODEL)

10. **1024 dims basta para busca híbrida — 2560 é overkill**
    - Em sistema híbrido, FTS5/BM25 cobre keywords, siglas, termos de código
    - Vetor só precisa resolver semântica, paráfrase e cross-lingual
    - 1024 dims × 596 chunks = ~2.4 MB em vetores. Leve.
    - Fallback: subir para 2560 só se observar perda real de recall
    - **Onde**: `config.py:47` (EMBEDDING_DIMENSIONS = 1024)

11. **embed_query vs embed_document é obrigatório para Qwen**
    - Qwen recomenda instrução explícita para queries de retrieval
    - Formato: `Instruct: {instruction}\nQuery: {text}`
    - Documentos vão crus, sem instrução
    - Sem essa separação, a qualidade do retrieval cai
    - **Onde**: `embeddings.py:65-72` (embed_query), `vector_store.py:49-60` (_embed_with_cache kind param)

12. **Cache de embedding deve incluir modelo+dims no hash**
    - Hash antigo: `sha256(text)` — colide se trocar modelo ou dimensão
    - Hash novo: `sha256(model:dims:text)` — evita reutilizar embedding incompatível
    - Full reindex limpa cache antigo automaticamente
    - **Onde**: `embeddings.py:53-55` (text_hash), `indexer.py:58-62` (DELETE embedding_cache no full)

13. **Trocar dimensão do vec0 exige DROP TABLE + CREATE**
    - `CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(...)` não altera dimensão se tabela já existe
    - No full reindex, é obrigatório dropar e recriar com a nova dimensão
    - **Onde**: `database.py:164-170` (recreate_vec_table), `indexer.py:58-62`

## 2026-03-25 — V02: Pipeline de busca com tolerância léxica

14. **Normalização de separadores resolve classe inteira de erros sem deps externas**
    - `sqlite-vec` e `sqlite_vec` e `sqlite vec` são tokens diferentes para FTS5
    - Solução: `re.sub(r'[-_]', ' ', text)` aplicada na query (não no índice)
    - Cobre: `total-recall`↔`total recall`, `session_id`↔`session id`
    - Não requer `--full` reindex — atua só em query-time
    - **Onde**: `vector_store.py:82-84` (_normalize_technical)

15. **Abreviações PT-BR e fuzzy devem ser processados em passada única sobre tokens crus**
    - Primeira tentativa: pipeline sequencial (abbreviations → fuzzy) falhava
    - O fuzzy recebia a query já formatada com `("vc" OR "você")` e corrompia a sintaxe FTS5
    - Solução: `_build_fts_query()` itera sobre tokens crus uma única vez — para cada token, checa abreviação primeiro, depois fuzzy
    - **Onde**: `vector_store.py:280-320` (_build_fts_query)

16. **OR entre grupos é obrigatório para queries multi-palavra**
    - FTS5 trata espaço entre tokens como AND implícito
    - `"como" "decidimos" "sobre" "sqlite"` exige TODOS os termos → muito restritivo
    - O `_sanitize_fts_query` antigo usava OR explícito; a V02 deve manter
    - BM25 naturalmente rankeia mais alto documentos com mais matches
    - **Onde**: `vector_store.py:318` (OR join)

17. **rapidfuzz (C++) é 257x mais rápido que Levenshtein em Python puro**
    - Benchmark real sobre vocabulário FTS5 do Total Recall (5.413 termos):
    - Python puro: ~48 ms por token, ~236 ms para pipeline de 5 tokens
    - rapidfuzz: 0.2 ms por token, 0.9 ms para pipeline de 5 tokens
    - Overhead sobre FTS5 puro: +0.2 ms (40% do baseline de 0.4 ms)
    - Em Python puro, a busca degradaria de 0.4 ms para ~48 ms — inaceitável
    - **Onde**: `vector_store.py:262-278` (_fuzzy_find_variants)

18. **fts5vocab é virtual table que precisa ser criada explicitamente**
    - O vocabulário do FTS5 não é diretamente acessível
    - `CREATE VIRTUAL TABLE chunks_fts_vocab USING fts5vocab('chunks_fts','row')` expõe os tokens
    - Cache de 60s evita recriar a cada busca
    - **Onde**: `vector_store.py:244-260` (_get_fts_vocabulary)

## 2026-03-25 — V02.2: Threshold adaptativo, fontes e otimização do indexer

19. **Threshold fixo de 85% é rígido demais para palavras curtas**
    - `fuzz.ratio` penaliza substituição como 2 operações (delete+insert)
    - 1 substituição em 4 chars = 75% (abaixo de 85%), em 5 chars = 80%, em 6 chars = 83.3%
    - Resultado: `ABSE→ABSA`, `Nuvex→novex`, `Mexton→maxton` falhavam com threshold 85%
    - Fix: threshold baixado para 70% — captura 1 substituição em qualquer palavra 4+ chars
    - **Onde**: `config.py` (FUZZY_THRESHOLD = 0.70)

20. **Doc count do fts5vocab é essencial para fuzzy inteligente**
    - Problema 1: termos comuns (como=182 docs, sobre=75) recebiam fuzzy desnecessário → ruído
    - Problema 2: termos raros que existiam no vocab (abse=3 docs) eram tratados como "exatos"
    - Solução: `_get_fts_vocabulary` retorna `{term: doc_count}` em vez de `set`
    - Heurística: `doc_count <= 10` → provável typo → expandir. `> 10` → termo real → literal
    - Tiebreaker: fuzzy com mesma similaridade prefere termos com mais docs (absa=52 > abel=1)
    - **Onde**: `vector_store.py` (_get_fts_vocabulary, _fuzzy_find_variants, _build_fts_query)

21. **Indexação append-only é 10-50x mais rápida que delete+re-insert**
    - Design original: sessão mudou → DELETE todos chunks → re-parse → re-insert tudo
    - Com sessão de 6.8 MB (386 chunks), cada index reprocessava tudo mesmo por 5 msgs novas
    - Fix: `_get_last_chunk_index()` identifica o último chunk indexado, pula os anteriores
    - JSONL do Claude Code é append-only por design → seguro pular chunks existentes
    - `--full` continua disponível para reindexação completa quando necessário
    - **Onde**: `indexer.py` (_get_last_chunk_index, _index_single_file skip_until)

22. **Atribuição de fonte por resultado permite diagnóstico de busca**
    - Cada SearchResult agora tem `sources: list[str]` (["vector"], ["fts5"], ["vector", "fts5"])
    - RecallContext inclui `query_info` com expansões fuzzy/abreviação aplicadas
    - Permite ao usuário entender POR QUE um resultado apareceu
    - **Onde**: `models.py` (SearchResult.sources), `vector_store.py` (hybrid_search tracking)

23. **Highlighting de termos funciona diferente por formato**
    - Terminal (rich): ANSI escape codes `\033[43m` (fundo amarelo) — visível direto no terminal
    - Markdown (context/recall): `**bold**` — Claude preserva na resposta ao usuário
    - Função `highlight_text()` genérica aceita mode="ansi" ou mode="markdown"
    - Termos da query original E das expansões são highlightados
    - **Onde**: `models.py` (highlight_text), `cli.py` (rich format), `models.py` (format_for_context)
