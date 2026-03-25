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
