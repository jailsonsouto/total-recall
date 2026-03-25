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
