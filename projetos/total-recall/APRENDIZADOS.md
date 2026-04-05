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

## 2026-03-26 — V02.3: Piso de confiança vetorial + diagnóstico de desequilíbrio estrutural

24. **Score máximo FTS5 (0.30) é estruturalmente inferior ao ruído vetorial (0.38–0.41)**
    - A ponderação 70/30 cria um teto assimétrico: FTS5 nunca pode marcar acima de TEXT_WEIGHT=0.30
    - Ruído vetorial (vetor de termo ausente do corpus) frequentemente supera 0.30, enterrando resultados FTS5 genuínos
    - Descoberta prática: busca por "netnografia" retornava 5 chunks de ruído vetorial (0.38–0.41) que mascaravam 8 resultados FTS5 legítimos (0.08–0.09) com a palavra literal no corpus
    - O desequilíbrio é mais grave para termos raros/técnicos/próprios — exatamente os mais valiosos para recuperação de memória

25. **FTS5 como prova de existência — sinal duro subestimado**
    - Se FTS5 encontrou o termo, ele *literalmente existe* no corpus: sinal binário e confiável
    - Resultado FTS5 = existência confirmada; resultado VECTOR = inferência probabilística
    - Na arquitetura atual, inferência probabilística fraca (ruído) derrota existência confirmada fraca (score baixo)
    - Fix aplicado: `MIN_VECTOR_ONLY_SCORE = 0.42` descarta resultados vector-only abaixo do piso
    - Resultados com contribuição FTS5 passam incondicionalmente — a existência literal sempre prevalece
    - **Onde**: `config.py` (MIN_VECTOR_ONLY_SCORE), `vector_store.py:hybrid_search()` (filtro seletivo)

26. **MIN_SCORE é workaround correto para agora, mas o design ideal é ponderação adaptativa**
    - O fix certo de longo prazo: detectar o tipo de query e ajustar pesos antes de buscar
    - Queries específicas/técnicas/raras → modo FTS5-dominante (ex: 20% vetor / 80% FTS5)
    - Queries semânticas/difusas → modo híbrido padrão (70% / 30%)
    - Sinal para classificação: doc_count no fts5vocab + morfologia do termo + presença de maiúsculas
    - Alternativa: normalizar cada modalidade dentro da sua própria distribuição antes de combinar
    - Implementação futura (V03): camada de roteamento de query antes do hybrid_search

27. **A skill /recall tem vantagem estrutural: Claude age como filtro inteligente pós-recuperação**
    - Antes do fix, /recall com "netnografia" funcionava corretamente mesmo recebendo ruído
    - Claude lê os chunks, percebe ausência de relação com a query, informa "não encontrado"
    - O CLI não tem esse buffer — exibia resultados com aparência de real, confundindo o usuário
    - Lição: sistemas com LLM na cadeia de interpretação toleram mais ruído na recuperação
    - Lição inversa: não confiar nessa tolerância como substituto de qualidade na recuperação

## 2026-03-26 — V03: Ponderação adaptativa de query

28. **Ponderação 70/30 é errada para queries técnicas — o classificador resolve isso dinamicamente**
    - Implementação de `_classify_query_weights()` que detecta o tipo de query antes de buscar
    - Três etapas: (1) stop words semânticas → híbrido; (2) query curta (≤2 tokens) → FTS5-dominante; (3) todos tokens técnicos → FTS5-dominante
    - Pesos adaptativos: `fts5_dominant` = 25% vetor / 75% FTS5 (configurável via env vars)
    - `search_mode` exposto em `--format json` para diagnóstico
    - Casos de uso: netnografia, MLEGCN, BERTimbau, PLN, NER — todos classificados corretamente como fts5_dominant
    - **Onde**: `vector_store.py:_classify_query_weights()`, `config.py` (ADAPTIVE_VECTOR_WEIGHT_SPECIFIC)

29. **V03.1: Acrônimos curtos ALL-CAPS (3 chars) eram invisíveis para o classificador**
    - `FUZZY_MIN_TOKEN_LENGTH = 4` filtrava PLN, NER, SQL, API, GPU — tokens de 3 letras nunca chegavam ao classificador como "significativos"
    - Fix: função `_is_meaningful()` que adiciona exceção para tokens ALL-CAPS de 2-3 letras
    - Extensão: padrão `_CAPS_PREFIX = re.compile(r'^[A-Z]{2,}')` captura nomes técnicos CamelCase (BERTimbau, GPT4, SQLite) na etapa 2b
    - 15/15 casos de teste passam: PLN, NER, NLP, SQL, API, GPU, PLN+NER+BERTimbau, MLEGCN e regressões
    - Regra geral: qualquer token que começa com 2+ maiúsculas é tratado como termo técnico, não como palavra comum
    - **Onde**: `vector_store.py:_classify_query_weights()` (função `_is_meaningful` + `_CAPS_PREFIX` em módulo)

## 2026-03-26 — Indexação automática via hooks do Claude Code

30. **SessionStart + PreCompact é a combinação correta para indexação automática**
    - `SessionEnd` parece óbvio mas é imprevisível: sessões podem fechar abruptamente sem disparar o hook
    - `SessionStart` é garantido: toda vez que o Claude Code abre, o índice é atualizado
    - `PreCompact` resolve o único gap real: conteúdo da sessão atual fica disponível via `/recall` mesmo após compactação
    - Sem `PreCompact`, conteúdo compactado só seria indexado no próximo `SessionStart` (próxima sessão)
    - Os dois hooks juntos eliminam a necessidade de indexação manual no dia a dia
    - **Onde**: `~/.claude/settings.json` (hooks SessionStart e PreCompact)

31. **Total Recall lê JSONL em disco, não o contexto ativo do Claude**
    - Compactação de contexto não apaga dados: os arquivos JSONL em `~/.claude/projects/` continuam crescendo
    - O que se perde na compactação é apenas a memória de trabalho do Claude, não o conteúdo em disco
    - Portanto, não há urgência em indexar ANTES da compactação para preservar dados
    - A urgência do `PreCompact` é outra: tornar o conteúdo pesquisável via `/recall` ainda naquela sessão

## 2026-03-26 — Revisão de arquitetura (relatório consolidado → V04)

32. **Append-only tem uma segunda camada de risco: mudança de parser sem reindexação**
    - O hash SHA-256 do JSONL não muda quando o parser é atualizado
    - O banco pode ter metade dos chunks indexados com a política antiga sem nenhum sinal visível
    - Fix: persistir hash de "versão do parser" em `indexing_runs`; discrepância deve sinalizar índice potencialmente stale
    - **Onde**: `indexer.py`, `database.py` (schema de `indexing_runs`)

33. **A degradação silenciosa para FTS5-only tem uma camada invisível: a skill não sabe**
    - Quando em modo degradado, o contexto injetado no Claude via `/recall` não carrega nenhum marcador de qualidade
    - A resposta gerada tem a mesma aparência de confiança de quando os embeddings estão ativos
    - Isso é calibração de confiança errada, não só ausência de observabilidade operacional
    - Fix: `doctor` command + marcador de modo na saída da skill

34. **O provider OpenAI tem dois problemas independentes: dimensão e instrução**
    - Dimensional (já documentado): banco cria chunks_vec com 1024 dims, OpenAI retorna 1536
    - Instrução (novo): OllamaEmbedProvider usa instruction-aware embedding; OpenAIEmbedProvider não passa instruções à API
    - text-embedding-3-small suporta instruções, mas o código não as usa — embeddings OpenAI são estruturalmente piores para retrieval, não por capacidade do modelo, mas por uso incorreto
    - **Onde**: `embeddings.py:OpenAIEmbedProvider`

35. **MMR usa Jaccard em vez de embeddings — a ferramenta errada para o problema certo**
    - Jaccard: "esses textos compartilham palavras"; cosine embedding: "esses textos expressam ideias próximas"
    - Pares semanticamente redundantes com vocabulário diferente passam pelo MMR; pares complementares com vocabulário similar são descartados
    - Os embeddings já estão no banco — custo de corrigir é baixo
    - **Onde**: `recall_engine.py` (cálculo de similaridade no MMR)

36. **Classificação adaptativa tem caso cego: queries mistas (stop words + termos técnicos)**
    - "Por que o PLN falhou com BERTimbau?" tem stop words semânticas E termos técnicos
    - Waterfall binária classifica como semântica (70/30) quando a intenção é técnica
    - Fix: interpolar pesos proporcionalmente quando os dois sinais coexistem
    - **Onde**: `vector_store.py:_classify_query_weights()`

37. **Threshold fuzzy absoluto (doc_count ≤ 10) degrada com crescimento do corpus**
    - Termos raros genuínos ficam acima do threshold e param de ser expandidos
    - Typos frequentes também ficam acima e param de ser corrigidos
    - Fix: usar frequência relativa (ex: < 0.1% do vocabulário total)
    - **Onde**: `vector_store.py:_build_fts_query()`

38. **Tentativas fracassadas e rejeições são sistematicamente ignoradas pela indexação**
    - Marcadores atuais capturam conclusões ("decidimos", "root cause") mas não rejeições
    - "Tentei X mas não funcionou", "descartamos A porque B", "o problema não era Z" — memória diagnóstica de alta densidade
    - Grande parte do conhecimento técnico reside em "o que não funciona e por quê"
    - Fix: adicionar marcadores de rejeição ao critério de seleção de blocos internos
    - **Onde**: `session_parser.py` (lista de markers para thinking/tool_result)

39. **Timestamp de chunk é o timestamp de sessão, não de mensagem**
    - Sessões longas (horas) têm todos os chunks com o mesmo timestamp
    - Temporal decay incorreto; mudanças de posição dentro da sessão são invisíveis
    - JSONL tem `createdAt` por mensagem — extração de timestamp por chunk é de custo baixo
    - **Onde**: `session_parser.py`, `models.py:Chunk`

40. **Overlap de chunking cria artefatos de scoring no FTS5 que reduzem o pool efetivo do MMR**
    - Termo na zona de overlap aparece em dois chunks adjacentes; ambos recebem match FTS5
    - Pool de 3x fica parcialmente ocupado por duplicatas antes de chegar ao MMR
    - Fix: deduplicação por chunk_id antes do MMR; considerar aumentar pool para 4x
    - **Onde**: `recall_engine.py`

41. **Clippings não são indexados — memória curada que não pode ser pesquisada**
    - `~/.total-recall/clips/` contém conteúdo selecionado pelo usuário, mas está fora do índice
    - Assimetria: a versão mais curada da memória é a menos recuperável
    - Fix: indexar clips como fonte de primeira classe com role weight diferente

42. **CONTEXT_BUDGET ignorado pode disparar a compactação que pretendia prevenir**
    - Em sessões longas, dump completo do /recall pode empurrar a sessão para o limiar de compactação
    - PreCompact dispara, indexa, mas o conteúdo entregue pela skill já foi compactado
    - Fix: aplicar CONTEXT_BUDGET real na skill com truncamento por score
    - **Onde**: `config.py:CONTEXT_BUDGET`, `recall_engine.py`, `skill/recall.md`

## 2026-04-05 — Análise Comparativa: Mecanismos de Memória

43. **Análise de 3 sistemas de memória de agentes (Hermes, memU, ZeroClaw)**
    - **Hermes Agent** (NousResearch): frozen snapshot pattern (brilhante para prefix caching), HRR com role binding (inovador mas SHA-256 não captura semântica), contradiction detection (único e valioso), trust scoring assimétrico (+0.05/-0.10)
    - **memU** (NevaMind-AI): salience scoring `sim × log(ref+1) × e^(-λ×days/half)` (superior ao decay simples), sufficiency gates com early termination (inteligente mas caro: 4-7 LLM calls/retrieval), tiered retrieval categories→items→resources
    - **ZeroClaw** (openagen): hybrid search FTS5+cosine em Rust (mais robusto dos 3), Soul Export (markdown versionável em git), hint-based embedding routing, embedding cache LRU, zero dependências externas no default path
    - **O que adotar**: frozen snapshot (Hermes), salience scoring (memU), hybrid search + cache LRU (ZeroClaw), contradiction detection (Hermes), Soul Export (ZeroClaw), hint-based routing (ZeroClaw)
    - **O que evitar**: LLM-heavy retrieval (memU), brute-force numpy (memU), HRR SHA-256 (Hermes), categorias estáticas (memU), dedup placeholder (memU)

44. **FTS5 já é BM25 — não faz sentido trocar**
    - O `rank()` do FTS5 implementa BM25 com k1=1.2 e b=0.75 hardcoded
    - Trocar FTS5 por "BM25 puro" seria trocar algo que funciona por algo que faz a mesma coisa com mais código
    - O gap real é FTS5 → SPLADE (expansão semântica neural), mas SPLADE requer GPU
    - Para uso local: FTS5 fica como camada lexical, semântica vem do vetor denso (qwen3), a ponte é expansão inteligente de query aprendida do corpus

45. **Graph Lite = co-ocorrência de entidades, não Neo4j**
    - 2 tabelas: `entities(id, name, type)` + `chunk_entities(chunk_id, entity_id)`
    - Permite: contradiction detection, compositional queries, navegação lateral
    - Extração: regex simples (backticks, ADR refs, project paths, capitalized terms)
    - Custo: ~200 linhas de código, zero dependências novas
    - Implementável no total-recall-codex desde o início

46. **Blueprint tri-hybrid para versão futura superior**
    - Query Classifier → TRI-HYBRID (FTS5 BM25 + Vector Dense + Graph Lite) → Salience Rerank → MMR Diversity → Contradiction Scan → Results + Provenance
    - Storage: SQLite único com FTS5 + sqlite-vec + tabela de entidades
    - Embeddings: Ollama local com cache LRU + hint-based routing
    - Export: Markdown versionável + JSONL para reindexação
    - Pragmaticamente bom sem ser elefante branco
