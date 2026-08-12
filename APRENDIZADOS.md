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

## 2026-07-05 — Delegação do /recall a sub-agente barato + diagnóstico de travamento

47. **`/recall` agora delega busca+síntese a um sub-agente (Agent tool, model=sonnet) em vez de rodar na sessão principal**
    - Motivação: a skill rodava `total-recall search` e lia os resultados brutos direto no modelo caro (Fable/Opus), gastando tokens do orquestrador em trabalho braçal (grep de transcript, formatação)
    - Novo fluxo: o orquestrador só faz parsing de flags (`--clip`, `--limit`, `--session`) e chama `Agent(subagent_type: "general-purpose", model: "sonnet", prompt: <self-contained>)`; o sub-agente roda o comando, lê e sintetiza, e devolve só a resposta final
    - O orquestrador relay a mensagem final do sub-agente sem re-executar a busca nem re-ler os resultados brutos
    - **Onde**: `skill/recall.md` E `~/.claude/skills/recall/SKILL.md` (cópia instalada — não é symlink, precisa editar as duas)
    - Refinamento pendente: o Agent tool não expõe "reasoning effort" como parâmetro direto (só `model`, `subagent_type`, `isolation`, `description`, `prompt`) — para fixar effort=medium/low seria preciso criar um agente customizado em `.claude/agents/*.md` com frontmatter próprio, ainda não feito

48. **Skills instaladas em `~/.claude/skills/` são snapshotadas no início da sessão — editar o arquivo em disco não muda o comportamento da sessão corrente**
    - Editei `~/.claude/skills/recall/SKILL.md` e confirmei via Read que o conteúdo novo estava salvo corretamente no disco
    - Ao invocar `/recall` na MESMA sessão para testar, o corpo da skill devolvido pelo harness ainda era o ANTIGO (pré-edição)
    - Conclusão: o Claude Code carrega/cacheia o corpo das skills no início da sessão (ou na primeira invocação); mudanças feitas depois só valem em uma sessão nova
    - Implicação prática: qualquer edição de skill precisa ser validada abrindo uma sessão nova, nunca dentro da sessão onde a edição foi feita

49. **Diagnóstico de sessão "travada": comando trivial sem tool_result é sinal de stall de transporte, não de carga de trabalho**
    - Sessão `ab393dc5` (apelidada "total-recall-vingador") ficou >1h sem responder; usuário reportou 98% de créditos Fable consumidos
    - Investigação no JSONL bruto (`~/.claude/projects/.../ab393dc5-*.jsonl`): o último `tool_use` antes do silêncio era `Bash: ls /Users/criacao/.claude/agents/ 2>&1` — comando local trivial, sem I/O em OneDrive, que deveria retornar em milissegundos
    - Não houve `tool_result` correspondente antes do gap de ~69 min; a mensagem de interrupção do usuário ("travou?") passou por um mecanismo de fila (`queue-operation: enqueue` → `popAll`) em vez de ser processada na hora
    - A sessão tinha um marcador `bridge-session` (`bridgeSessionId`), sugerindo execução via relay/ponte — stall mais provável é na camada de transporte da ponte, não em processamento pesado ou lentidão do modelo
    - **Lição geral**: quando uma sessão "trava", olhar o JSONL bruto e achar o ÚLTIMO `tool_use` sem `tool_result` correspondente. Se o comando travado é trivial (ex.: `ls` num diretório local), é sinal de falha de transporte/infra, não de carga de trabalho — não adianta esperar mais nem trocar de modelo, é preciso reiniciar a sessão
    - **Onde**: nenhum código do projeto — é um padrão de diagnóstico via `~/.claude/projects/<projeto>/<session-id>.jsonl`

## 2026-07-05 — Advisor tool, FastContext e estudo empírico do formato de resposta

23. **O rank não prediz utilidade nos resultados do recall — sessão nova prediz**
    - Estudo empírico (5 últimas buscas reais re-executadas com `--limit 8 --format json`)
    - Em 3/5 queries, evidência não-redundante apareceu nos ranks 4-8 (num caso, o alerta
      crítico estava no rank 8); ruído e substância vêm intercalados
    - Corte cego "top-3 + ponteiros" seria regressão; o corte certo é dedupe por sessão
    - **Onde**: `models.py::format_pointers` (dedupe por sessão), skill /recall (síntese
      por sessão distinta), `docs/PLANO-ADVISOR-FASTCONTEXT-2026-07-05.md` §3

24. **O índice está se auto-contaminando com eco do próprio /recall**
    - Comandos `total-recall search` ecoados, "busca em segundo plano" e task-notifications
      viram chunks e rankeiam alto nas buscas seguintes
    - Mitigação provisória: regra de descarte no prompt do sub-agente do /recall
    - Fix definitivo pendente: filtro de padrões de eco no `session_parser.py`
      (backlog em `docs/PLANO-ADVISOR-FASTCONTEXT-2026-07-05.md` §4.1)

25. **Bug de deploy: o binário instalado estava congelado desde 16/maio**
    - O `pip` de `~/.venvs/total-recall-py312/bin/` aponta para o venv do CODEX
      (`total-recall-codex-py312`) — instalações por ele nunca chegavam ao venv certo
    - Agravantes: wheel em cache do pip e `build/` obsoleto na cópia de deploy
    - Fluxo correto: `rsync src/ → ~/.local/share/total-recall-app/src/` e depois
      `~/.venvs/total-recall-py312/bin/python -m pip install --no-cache-dir --force-reinstall --no-deps ~/.local/share/total-recall-app`
    - Sintoma para detectar recorrência: mudança no código não aparece no CLI

26. **Advisor tool (Anthropic) não é utilizável de dentro de skills do Claude Code**
    - É server tool da Messages API; skills não controlam o array de tools do harness
    - Aproveitamos só os padrões de prompt (reconciliação nomeada, cap de output,
      coletor-barato/julgador-forte) — detalhes no plano em docs/

27. **FastContext (Microsoft) validou o desenho do /recall e tem modelos públicos**
    - `microsoft/FastContext-1.0-4B-{SFT,RL}` (MIT) + GGUFs prontos para Ollama
    - Treinado para explorar código, não transcripts — não substitui o total-recall
    - Experimento futuro (explorador de código local) registrado no plano §4.3

## 2026-07-29 — /btw é inelegível para indexação: efêmero por design, sem hook

50. **`/btw` (side-question panel) não deixa rastro capturável — não é lacuna do parser, é design deliberado**
    - Confirmado via doc oficial (`code.claude.com/docs/en/interactive-mode.md`): "side questions don't become part of the permanent conversation history" — resposta é descartada, não persistida em JSONL nem em arquivo separado
    - Confirmado empiricamente: nenhuma entrada com `isSidechain: true`, nenhum `type` novo, nenhum diretório `~/.claude/btw/` nos 121 transcripts locais
    - Confirmado que não há hook disponível: `/btw` é processado inteiramente client-side (overlay da UI), não dispara `UserPromptSubmit`, `Stop`, `SubagentStop` nem nenhum dos 24 hook events documentados — bypassa o pipeline de eventos que geraria dados capturáveis
    - Doc de sub-agents contrasta explicitamente: `/btw` "sees your full context but has no tool access, and the answer is discarded rather than added to history" — é o oposto de um subagent, não uma sessão paralela indexável
    - **Único caminho de persistência existente**: a tecla `f` no overlay do `/btw` forka a pergunta+resposta para o histórico real da sessão como turns normais `user`/`assistant` — quando isso acontece, o `session_parser.py` já indexa automaticamente, sem precisar de nenhuma mudança de código
    - **Onde**: nenhum código do projeto — decisão de não implementar, documentada aqui para não re-investigar no futuro se o pedido voltar

## 2026-07-29 — Indexação de subagentes: bug do isSidechain, filtro de ruído e lock contention

51. **`isSidechain: true` nunca aparece intercalado em arquivo de sessão principal — só existe em arquivos dedicados `.../subagents/agent-*.jsonl`, onde é 100% do conteúdo**
    - O parser filtrava `isSidechain=True` incondicionalmente em `_build_chunks()` e `_extract_session_info()`, pensado para excluir conteúdo redundante intercalado
    - Verificação empírica em 380 arquivos JSONL (121 sessões principais + subagentes): 14.868 entradas `isSidechain=true`, TODAS dentro de arquivos de subagente, ZERO intercaladas em sessão principal
    - Resultado: mesmo com `total-recall index --subagents` (flag já existia, mas morta), todo arquivo de subagente gerava 0 chunks — confirmado num arquivo real (16 mensagens → 0 chunks antes do fix, 14 chunks depois)
    - Fix: filtro condicional a `"subagent" in str(file_path)` — dentro de arquivo de subagente, isSidechain=true é indexado normalmente
    - **Onde**: `session_parser.py` (`_is_subagent_file`, `_extract_session_info`, `_build_chunks`)

52. **Metadados `attributionSkill`/`attributionAgent` no JSONL identificam de qual skill/tipo de agente veio um subagente — essencial para filtrar ruído**
    - Cada entrada de arquivo de subagente carrega `attributionAgent` (general-purpose, Explore, fork, claude-code-guide, Plan) e `attributionSkill` (recall, brainiac, opsx:apply, modo-tcc, ...) quando disparado de dentro de uma skill
    - Achado: quase metade dos subagentes do usuário (496 de ~1000 mensagens) vêm da skill `/recall` — eco de buscas e sínteses, exatamente o ruído de auto-contaminação já documentado no item 24 (2026-07-05)
    - Fix: `SessionDiscovery._scan_subagent_file()` calcula hash e detecta `attributionSkill in {"recall"}` numa única passada; arquivos ruidosos são pulados antes mesmo de entrar no pipeline de parse
    - Bônus: os mesmos campos alimentam o título de fallback (`Subagent {agent} ({skill})`) em `session_parser.py`, melhorando a legibilidade dos resultados de busca
    - **Onde**: `session_discovery.py` (`_NOISE_ATTRIBUTION_SKILLS`, `_scan_subagent_file`), `session_parser.py` (título)

53. **Embedding (chamada de rede ao Ollama) dentro de uma transação SQLite de escrita é uma bomba-relógio de lock contention**
    - `indexer.py::_index_single_file` abre `with self.db.transaction()` e, para CADA chunk, chama `vector_store.add(..., _conn=conn)`, que gera o embedding via Ollama dentro da MESMA transação — o lock de escrita fica preso pela duração de N chamadas de rede, não de N inserts locais
    - `database.py::_get_connection` não definia `timeout` no `sqlite3.connect()` → default do Python é 5s
    - Sintoma real: reindex de subagentes em background (arquivos com até 32 chunks, várias dezenas de segundos de lock) colidiu com `total-recall index` manual do usuário em outro terminal → `sqlite3.OperationalError: database is locked`, comando abortou sem escrever nada (sem corrupção, só falha de aquisição de lock)
    - Fix aplicado (rápido, seguro): `timeout=60.0` no `sqlite3.connect()` — segundo escritor espera em vez de falhar na hora
    - **Fix estrutural pendente (não aplicado ainda)**: separar a resolução de embedding (rede, pode ser lenta) da transação de escrita (deveria ser só inserts locais, rápidos) — reduziria a janela de lock de "segundos-minutos" para "milissegundos" e tornaria o timeout de 60s quase nunca necessário. Ganhou mais urgência porque os hooks agora rodam `--subagents` (runs mais pesados) em todo SessionStart/PreCompact — duas sessões do Claude Code abrindo perto uma da outra colidem com mais frequência
    - **Onde**: `database.py:_get_connection` (fix aplicado), `indexer.py:_index_single_file` + `vector_store.py:add/_embed_with_cache` (fix estrutural pendente)

## 2026-08-03 — Busca cruzada (read-only) com o total-recall-codex

54. **Handoff de outra sessão descrevia a implementação-espelho do codex (`67cd244`) corretamente na tese, mas errado em dois detalhes de transcrição — validar contra o commit real antes de portar, não só contra a prosa do handoff**
    - O snippet de `database.py` proposto no handoff omitia `PRAGMA journal_mode = WAL` e `PRAGMA foreign_keys = ON` dos dois ramos — inclusive do ramo de escrita normal. Colado ao pé da letra, seria uma regressão real no banco principal (perderia WAL mode), não só um detalhe do modo read-only. O commit original do codex guarda essas duas PRAGMAs corretamente com `if not self.read_only:` — não as omite. Fix: preservado o guard, PRAGMAs continuam no ramo de escrita (coberto por `TestWritePathUnaffected` em `test_crossover.py`)
    - O handoff assumia que `RecallContext` tem três métodos de formatação (`format_rich`, `format_for_context`, `to_dict`) espelhando `models.py` do codex. Neste projeto só dois existem como método (`format_for_context`, `format_pointers`) — os formatos "rich" (o padrão da CLI) e "json" são código solto dentro de `cli.py::search()`, não métodos da classe. A marcação de origem precisou tocar 5 pontos (2 em `models.py`, 2 em `cli.py`, mais o bloco "rest"/ponteiros-de-1-linha de `format_pointers` que antes não mostrava nenhum indicador de fonte), não 3
    - **Onde**: `docs/HANDOFF_2026-08-03_CROSSOVER-COM-CODEX.md` (handoff original), correções aplicadas em `database.py`, `models.py`, `cli.py`

55. **Decisão de produto: `--source both` é o padrão, não opt-in — "o projeto é a coleção" (memória coletiva > isolamento por padrão)**
    - O handoff original propunha `claude-code` (self) como default e busca cruzada só sob frase-gatilho ("cruzada"/"cross"), espelhando a postura isolada-por-padrão do codex (lá o default é `codex`, o próprio banco)
    - Usuário reformulou o objetivo: o valor do total-recall é lembrar decisões/conversas/caminhos alternativos independente de qual harness (Claude Code CLI ou Codex) foi usado — busca cruzada opt-in exigiria lembrar a frase-gatilho justamente no momento em que a resposta pode estar "no outro lado" e o usuário não sabe disso de antemão
    - Efeito colateral bom: como o default virou `both`, o hint de drill-down do `format_pointers()` (`total-recall search "..." --session <id> --format context`) e o passo 4 da skill (`--session <session-id> --limit 15`) funcionam corretamente sem precisar propagar `--source` por resultado — o filtro de sessão naturalmente bate só no banco dono daquele session_id, o outro engine retorna vazio
    - Trade-off aceito, não escondido: toda busca (mesmo quando a resposta está só localmente) paga o custo de abrir a segunda conexão e rodar `hybrid_search` duas vezes; se o banco irmão não existir, `both` avisa em stderr e segue só com o local (não quebra), `--source codex` sozinho sem banco irmão dá erro claro
    - Origem sempre marcada (`[CLAUDE-CODE]`/`[CODEX]`) em todos os formatos, inclusive quando é o banco local — o padrão do codex só marca a origem "estrangeira" (`if r.origin != "codex"`), o que obrigaria o leitor a inferir o local por ausência de marca; decidido marcar os dois sempre
    - **Onde**: `config.py` (`SIBLING_DB_PATH`), `database.py` (`read_only`), `models.py` (`SearchResult.origin`, `origin_label`, `format_for_context`, `format_pointers`), `recall_engine.py` (`recall_cross`), `cli.py` (`--source`, `_build_sibling_engine`), `skill/recall.md`, `tests/test_crossover.py`

56. **Reversão do item 55 na mesma sessão: `--source` volta a ter `claude-code` como padrão, busca cruzada volta a ser opt-in**
    - Motivo trazido pelo usuário: quer simetria com o `total-recall-codex` (lá o padrão é `codex`, o próprio banco — `both` por padrão aqui quebrava essa simetria, criando uma assimetria sem necessidade real)
    - Motivo técnico que reforça a escolha: `recall_cross()` chama `engine.recall()` por banco, e cada `RecallEngine.recall()` embeda a query via `hybrid_search()` — como o `embedding_cache` é por arquivo SQLite (não compartilhado entre os dois bancos), toda busca com `--source both` paga DUAS idas reais ao Ollama pra mesma query, mesmo quando a resposta só interessa localmente. Com `both` como padrão, esse custo caía em toda chamada do `/recall`, não só nas que precisavam de cobertura cruzada
    - Fix: `cli.py` (`--source` default volta a `claude-code`), `models.py` (hint de drill-down do `format_pointers()` volta a exigir `--source <origem>` explícito — o "de graça" que o item 55 registrou como efeito colateral bom do `both`-padrão deixou de existir), `skill/recall.md` (sem flag = local; frase-gatilho pra cruzada volta a ser `cruzada`/`cross`; passo 4 de drill-down volta a checar o rótulo de origem do resultado antes de repetir a busca)
    - **Onde**: mesmos arquivos do item 55, revertendo só a escolha de default — o resto do desenho (origem sempre marcada, isolamento read-only, fusão em memória) não mudou

## 2026-08-03 — Preview truncado escondia matches genuínos; validado empiricamente com Haiku (3 rodadas)

57. **`--format rich`/`pointers` mostravam sempre `content[:N]` — se o termo buscado caísse fora da janela fixa, um resultado correto e bem rankeado parecia ruído**
    - Achado em produção pelo usuário: `total-recall search "duckdb analista" --source both --format rich` trouxe 5 chunks corretos (FTS5 bateu, scores 0.11–0.25), mas **nenhum preview mostrava "duckdb" nem "analista"** — verificado com `--format context` que os termos estavam lá, só fora dos 300 chars iniciais de chunks de até `MAX_CHUNK_CHARS`=1500
    - **Validação empírica com sub-agent Haiku, sem contexto prévio**, pedido pra avaliar o output honestamente: ANTES do fix, concluiu com confiança "isso é ruído, a busca não funcionou", e inventou uma explicação plausível mas errada ("semantic drift", "FTS5 scores extremamente baixos" — falso, 3 dos 5 resultados tinham contribuição FTS5 real). Prova concreta de que o bug não era só estético — um sub-agente fraco consumindo esse formato daria uma resposta errada e convicta ao usuário
    - Fix 1: `preview_window()` em `models.py` — centraliza a janela no primeiro termo encontrado (prioriza a query literal sobre expansões fuzzy/abreviação — uma expansão ruidosa tipo "wren"→"when" pode achar uma posição sem relação com a busca real). Aplicado em `cli.py` (rich, 300 chars) e `models.py::format_pointers()` bloco "rest" (pointers, 120 chars)
    - **Segunda rodada de Haiku (pós fix 1)**: confirmou que os termos agora aparecem nos previews, mas achou um problema residual real — um chunk com "duckdb" E "analista" a ~150 chars de distância (mesmo bloco mermaid) só mostrava UM dos dois na janela de largura fixa, fazendo um match completo parecer parcial
    - Fix 2: `preview_window()` ganhou `max_width` (padrão 2×`width`) — quando mais de um termo distinto aparece no conteúdo e a distância entre eles cabe no `max_width`, a janela expande pra cobrir do primeiro ao último; se estiverem longe demais, cai de volta pra centralizar só no primeiro
    - **Terceira rodada de Haiku (pós fix 2)**: identificou corretamente o chunk do diagrama mermaid como "GENUINE MATCH — both terms in same diagram context". Veredito final do Haiku ("só 1 de 5 tem os dois termos juntos, os outros são hits parciais de um termo só") deixou de ser um bug da ferramenta e virou uma leitura literal correta do corpus — nem todo chunk que menciona "duckdb" ou "analista" isoladamente devia mesmo aparecer como match forte pros dois juntos
    - Metodologia replicável: sempre que um formato de saída for consumido por um sub-agente (não só por um humano no terminal), validar com o modelo mais fraco da cadeia (Haiku), não só com o mais forte — o que é óbvio pra quem já sabe a resposta pode enganar quem está vendo o output pela primeira vez
    - **Onde**: `models.py` (`preview_window`, `extract_query_terms`, `_find_term_positions`, `_find_first_term_pos`, `format_pointers` bloco "rest"), `cli.py` (bloco `rich`), `tests/test_preview_window.py` (23 testes, incluindo reprodução exata do chunk mermaid real)

## 2026-08-03 — Três bugs reais de score/preview corrigidos; um quarto investigado e conscientemente NÃO corrigido

58. **`preview_window()` ignorava termo fuzzy quando o termo literal já tinha ancorado a janela**
    - Achado com dado real: query "buscla vetorial" ("buscla" → fuzzy pra "busca"/"buscar"/"buscas", "vetorial" literal) — a barra de cobertura diria "①fuzzy ②literal", mas o trecho só mostrava "vetorial", nunca "buscar", mesmo estando no mesmo chunk. `priority_terms` (literal) achando QUALQUER posição fazia `fallback_terms` (fuzzy) ser ignorado por completo, não só "perder prioridade"
    - Fix: quando `priority_terms` ancora ao menos 1 posição, `fallback_terms` agora ESTENDE a janela (funde as posições, recalcula span) em vez de ser descartado; se a extensão não couber em `max_width`, volta a centralizar só nas posições literais (preserva o comportamento protetor original — um teste antigo pegou essa regressão na primeira tentativa do fix, corrigido antes de seguir)
    - **Onde**: `models.py::preview_window()`, `tests/test_preview_window.py` (5 testes novos)

59. **Fórmula do score FTS5 invertida: match mais forte pontuava PIOR** *(mesmo bug do item 3 do handoff de crossover, agora efetivamente corrigido — tinha ficado só diagnosticado na sessão anterior)*
    - `keyword_search()`: `score = 1.0 / (1.0 + rank)`, onde `rank` já é `abs(bm25_rank)` — cresce com a força do match (bm25 do SQLite é mais negativo quanto melhor, `abs()` inverteu o sinal). A fórmula antiga DECRESCE com rank maior — direção oposta
    - Verificado empiricamente (antes do fix): "aste OR absa", melhor match (rank=-9.9275) → score=0.0915 (o MENOR score do lote); 8º melhor (rank=-8.8906) → score=0.1011 (maior que o do 1º lugar)
    - Fix: `score = rank / (1.0 + rank)` — mesma faixa [0,1), direção certa
    - **Onde**: `vector_store.py::keyword_search()`, `tests/test_fts5_score.py`

60. **Bug pré-existente exposto pelo fix do item 59: `hybrid_search()` deduplicava por prefixo de texto, não por `chunk_id` — somava contribuições de chunks quase-duplicados**
    - A chave de merge era `f"{session_id}:{content[:100]}"`. Quando a mesma sessão tem N chunks DIFERENTES (chunk_id distintos) com os mesmos ~100 chars iniciais — ex.: o mesmo README colado 4x numa sessão Codex — o `+=` do merge somava a contribuição de texto das 4 vezes num resultado só
    - Ficou invisível enquanto o score do item 59 estava quebrado (scores uniformemente pequenos, ~0.05-0.15, escondiam o acúmulo). O fix do item 59 tornou os scores individuais maiores/mais diferenciados, e o acúmulo passou a estourar o teto teórico: **score=2.74 numa busca real** ("buscla vetorial"), matematicamente impossível já que `vector_weight + text_weight` sempre soma 1.0
    - Fix: chave de dedup trocada pra `chunk_id` (rowid compartilhado entre `chunks_vec` e `chunks_fts`, ambos apontam pra `chunks.id` — preciso, sem colisão), no lugar do prefixo de texto (aproximação frágil que colide em conteúdo quase-duplicado)
    - **Onde**: `vector_store.py::hybrid_search()`, `tests/test_fts5_score.py` (3 testes novos, `TestHybridSearchDedup`)
    - Lição: corrigir um bug de escala pode expor um segundo bug de lógica que só se torna visível na escala nova — sempre reverificar com dado real depois de um fix de fórmula, não só rodar a suíte de testes

61. **Achado 2 do handoff anterior (FTS5 passa incondicionalmente o piso de confiança, mesmo via match só-fuzzy) — investigado, conscientemente NÃO corrigido**
    - Hipótese de fix: exigir presença literal de termo da query (ou de suas expansões rastreadas) pra isentar do piso `MIN_VECTOR_ONLY_SCORE`
    - Testado com números reais antes de implementar (pedido do usuário: "tenha certeza que trazem ganho"): `fuzz.ratio` e proporção de comprimento NÃO distinguem o caso bom do caso ruim. `wren`→`wrenai` (validado como bom) e `photosynthesis`→`synthesis` (o falso positivo achado) têm perfis quase idênticos — ratio 80.0 vs 78.3, proporção de comprimento 0.67 vs 0.64
    - Conclusão: a diferença entre os dois casos é SEMÂNTICA (wren/wrenai são o mesmo produto; photosynthesis/synthesis são conceitos diferentes que só parecem parecidos como string), não sintática — nenhum guard baseado em string (rapidfuzz ratio, comprimento) resolve isso de forma confiável. Corrigir de verdade exigiria checagem semântica (embedding) na hora de aceitar candidato fuzzy, uma mudança de escopo maior (custo de latência: chamada Ollama extra por token raro/candidato)
    - Decisão: não implementar um fix que eu já provei, com dado real, que não resolveria o caso concreto e arriscaria quebrar casos já validados. Registrado como backlog de escopo maior, não como pendência simples
    - **Onde**: nenhum código alterado — decisão documentada aqui para não re-investigar do zero se o pedido voltar

62. **Split de palavra composta colada (`ducklake`→`duck lake`, `deltalake`→`delta lake`) — implementado depois de descartar duas alternativas de vetor com dado real**
    - Motivação: usuário testou "deltalake"/"ducklake" e achou que não estavam sendo tratados como "delta lake"/"duck lake" (nomes reais de produto, com espaço, como aparecem no corpus). Confirmado: FTS5 tokeniza "Delta Lake" como 2 tokens, "deltalake" é 1 token — nunca batem via match literal
    - **Duas alternativas de vetor testadas e descartadas com dado real, não só teoria** (item 61 já tinha descartado o Gatilho B por causa de "photosynthesis"/"synthesis" — esta sessão generalizou o achado):
      - Cosseno isolado (`embed_document` das duas frases direto uma contra a outra, sem instrução): 0.95-0.97 — parecia prometer muito
      - Mas na busca REAL (`search()`, que usa `embed_query` com instrução pra query e `embed_document` pro conteúdo, contra um corpus grande e diverso): "duck lake" não aparece em NENHUM dos 30 primeiros candidatos pra query "ducklake" — nem com instrução, nem sem (testado as duas formas). Cosseno isolado entre duas frases não prediz recuperação num corpus real com milhares de outros documentos competindo
      - "deltalake" foi um caso limítrofe: o match real ficou em 1º/2º lugar no vetor puro, mas com margem de ~1% sobre o "ruído" ao redor (0.6158 vs 0.60-0.61) — sinal fino demais pra generalizar um gatilho de reponderação com confiança
    - Fix implementado: `_find_compound_split()` — quando um token é raro/ausente (mesmo gatilho do fuzzy, `doc_count <= 10`), tenta cada ponto de corte e só aceita a divisão se AMBAS as metades existirem de verdade no vocabulário do corpus (evita splits sem sentido tipo "d"+"eltalake"). A frase resultante ("duck lake") entra como alternativa adicional no OR-group do FTS5, ao lado das variantes fuzzy — não substitui o fuzzy, complementa
    - Bug pequeno encontrado e corrigido na mesma leva: a linha "Expansões" trunca em `[:3]` pra exibição — com 5 variantes fuzzy já ocupando a lista, o split (adicionado por último) sumia da vista mesmo contribuindo pro resultado real. Fix: split entra PRIMEIRO na lista de exibição, sobrevive ao corte
    - Também corrigido: os 3 pontos que rotulavam tipo de expansão (`cli.py` + `models.py` ×2) tinham um `else` genérico que rotularia um tipo novo como "abrev" por engano — trocado por `expansion_label()` centralizado com fallback seguro (mostra o próprio tipo, não inventa rótulo errado)
    - Validado empiricamente: "ducklake" e "deltalake" agora encontram o conteúdo real ("Concorrência e DuckLake", "Rust implementation of the Delta Lake table format") nos primeiros resultados
    - **Onde**: `vector_store.py` (`_find_compound_split`, `_build_fts_query`), `models.py` (`expansion_label`), `cli.py`, `tests/test_compound_split.py` (9 testes)

63. **`--format table`: barra de cobertura por termo (░▒█) — codificação da exploração de design que ocupou boa parte desta sessão**
    - Substitui, como formato opcional (não default — `rich`/`context`/`pointers`/`json` continuam intactos), o score decimal bruto por um selo verificável por termo da query: `█` bateu literal, `▒` só via fuzzy/abreviação, `░` não apareceu. Cada símbolo é um fato checável no próprio conteúdo, não uma conta interna de pesos adaptativos
    - `%` é relativo ao melhor resultado *daquela busca* (topo=100%) — comparável dentro da lista (é a mesma ordenação do ranking), não entre buscas diferentes, ao contrário do score bruto que motivou toda a investigação (itens 57-59)
    - Processo de design: 3 propostas de painel geradas e comparadas com dado real (tabular / semáforo+trecho / barra recalibrada), fusão pedida pelo usuário (tabela + barra segmentada), validado com sub-agent Haiku em 3 rodadas ao longo da sessão, refinado por 2 achados reais de bug encontrados testando com fuzzy de verdade (preview_window não mostrava termo fuzzy quando literal ancorava — item 58; FTS5 passava incondicionalmente o piso de confiança — item 61, investigado e conscientemente não corrigido)
    - Validação final: "duckdb analista" e "ASTE ABSA" mostram exatamente o comportamento desenhado — um resultado com os dois segmentos acesos aparece com clareza mesmo fora do topo do ranking por score
    - **Onde**: `models.py` (`term_coverage`, `render_coverage_bar`, `relative_percent`, `circled_number`, `origin_plain`, `COVERAGE_LEGEND`), `cli.py` (`_print_table_format`), `README.md`, `docs/GUIA-USUARIO.md`, `tests/test_table_format.py` (21 testes)

64. **`term_coverage()` não removia acento — barra mostrava "ausente" pra match fuzzy real, achado pelo usuário no primeiro uso real do `--format table`**
    - Usuário comparou visualmente "ducklake" (barra 100% literal) com "proxmox" (barra quase toda fuzzy) e perguntou por quê. Investigação revelou dois fatos distintos, não um bug: "ducklake" bate literal porque nesse corpus o produto é escrito "DuckLake" (uma palavra, tipo GitHub) — diferente de "Delta Lake" (duas palavras, por isso precisou do split do item 62. "proxmox" expandiu fuzzy pra `proximo, promo, proximos, roxo, prom` — nenhuma relação com o software Proxmox, o mesmo padrão de falso positivo do "photosynthesis→synthesis" (item 61) — a barra tá certa em mostrar isso como ruído
    - Mas um resultado específico (conteúdo real: "**Próximo** check: 09:50", com acento) aparecia como `░░░░░░░░░░` (nenhum termo bateu) mesmo tendo vindo via FTS5 — inconsistência real: se o FTS5 achou, uma das alternativas do OR-group bateu de verdade
    - Causa: o tokenizer padrão do FTS5 (`unicode61`) remove acento por padrão — "próximo" e "proximo" são o mesmo token pro índice. `term_coverage()` comparava string crua em Python, sem essa normalização — `"proximo" in "próximo check".lower()` dá `False`
    - Fix: `_strip_accents()` (NFKD + remove caracteres combinantes) aplicado nos dois lados da comparação (termo da query/variante fuzzy E conteúdo) antes de checar presença — espelha exatamente a normalização que o FTS5 já faz
    - **Onde**: `models.py` (`_strip_accents`, `term_coverage`), `tests/test_table_format.py` (2 testes novos: fuzzy e literal com acento)

65. **Legenda de `--format table` sumia por completo em query sem termo válido — usuário perguntou "a legenda aparece?" e a resposta era "não, nesse caso não"**
    - Query com só palavras de 1 char (ex.: `total-recall search "a"`) faz `extract_query_terms()` retornar lista vazia — o `if query_terms:` que imprime a linha "Termos: ..." pulava inteiro, e `render_coverage_bar([])` retornava `"[]"` (colchete vazio, parece bug de exibição) em toda linha, sem nenhuma explicação
    - Fix: `render_coverage_bar([])` agora retorna `"—"` (trace claro de "nada pra mostrar aqui, de propósito", não colchete vazio); `_print_table_format()` ganhou um `else` explícito explicando por que não há barra de cobertura nesse caso, em vez de omitir a linha silenciosamente
    - Validado ao vivo: `total-recall search "a" --format table` agora mostra "Termos: nenhum termo específico o suficiente pra medir cobertura — resultados ordenados só por relevância" e `—` em cada linha
    - **Onde**: `models.py` (`render_coverage_bar`), `cli.py` (`_print_table_format`), `tests/test_table_format.py`

## 2026-08-12 — `total-recall backup` (comando nativo, compactado em .zip) + subagentes incluídos por padrão

66. **`TOTAL_RECALL_INDEX_SUBAGENTS` — default trocado de `false` pra `true`**
    - Pedido explícito do usuário: indexar conversas principais + subagentes juntos, sem precisar lembrar de `--subagents` toda vez. O filtro de ruído por atribuição (skill `recall`, ver item da sessão de crossover) continua ativo independente do default — o que mudou é só a inclusão/exclusão em massa
    - Documentação (README, GUIA-USUARIO) tinha que ser atualizada em conjunto: a frase "excluídos por padrão" ficaria enganosa depois do flip. Flag oposta (`--no-subagents`) passou a ser a forma de opt-out
    - **Onde**: `config.py:124`, `README.md`, `docs/GUIA-USUARIO.md` (seções 1 e 5)

67. **`total-recall backup`: SQLite Backup API + compactação em .zip — não é `cp`, e não é a etapa intermediária crua**
    - Requisito do usuário, refinado em duas rodadas: primeiro pedido foi "backup nativo, destino Desktop com fallback, cobrindo todos os bancos". Implementação inicial copiou os `.db` crus (via Backup API, seguro) pra uma subpasta com timestamp — mas o usuário já tinha pedido zip e a primeira entrega não zipou. Corrigido: agora o `.db` cru só existe numa pasta temporária do SO durante a execução, é compactado (`zipfile.ZIP_DEFLATED`) pra dentro de um único `.zip` e a pasta temporária é descartada — nunca sobra `.db` cru no destino
    - Lição prática: quando o pedido já inclui uma característica específica ("zipado"), tratar como requisito obrigatório, não como "sugestão pra considerar depois" — a sugestão de compressão foi oferecida no fim da resposta anterior como item *extra* quando na verdade já fazia parte do pedido original
    - Redução real medida com os dois bancos de produção (não sintético): 1103.5 MB → 570.2 MB (~48%) — texto de sessão comprime bem, embeddings (blobs float32) quase nada, por isso a redução fica bem abaixo do que zip costuma entregar em texto puro
    - Resolução de destino: `~/Desktop/` se existir e o SO for macOS; caso contrário (SO diferente, ou Desktop ausente), pergunta interativamente — `--output` pula essa lógica inteira (necessário pra cron/launchd, senão trava esperando stdin). `--keep N` poda os `.zip` mais antigos da pasta depois do backup atual
    - Módulo novo (`backup.py`) deliberadamente sem `import click` — só `cli.py` fala com o terminal (prompts, `click.progressbar`); o módulo de negócio fica testável sem simular tty/stdin. Mesma separação já usada em `indexer.py`/`cold_export.py`
    - Validado com integridade real: `.zip` extraído, `PRAGMA integrity_check` = `ok` nos dois `.db`, contagem de linhas em `sessions`/`chunks` batendo com o banco original
    - **Onde**: `backup.py` (módulo novo), `cli.py` (`backup` command), `tests/test_backup.py` (15 testes), `docs/BACKUP-E-RESTAURACAO.md`, `README.md`, `docs/GUIA-USUARIO.md` (seção 12 nova)

68. **Ambiente: `pip` dentro de `~/.venvs/total-recall-py312/bin/` tem shebang apontando pro Python de outro venv (`total-recall-codex-py312`) — reinstalação foi parar silenciosamente no lugar errado**
    - `~/.venvs/total-recall-py312/bin/pip --version` reportava rodando a partir de `total-recall-codex-py312/lib/.../pip` — pré-existente, não introduzido nesta sessão. `pip install --upgrade` executado com esse script instalou (com sucesso aparente, sem erro) dentro do site-packages do venv **errado**, deixando o pacote real (`total-recall-py312/site-packages/total_recall/`) intocado e desatualizado
    - Diagnóstico: `head -1 <venv>/bin/pip` mostra o shebang real — comparar com `pyvenv.cfg`/`sys.executable` do próprio venv resolve a suspeita rápido
    - Contorno: `python3 -m pip install ...` usa o interpretador do venv diretamente (`sys.executable`), ignorando o shebang do script `/bin/pip` — resolve sem precisar consertar o venv em si
    - Efeito colateral verificado (não uma regressão): o venv `total-recall-codex-py312` já tinha uma cópia própria do pacote `total-recall` instalada (usada nos testes do repo `total-recall-codex`, que fazem `import total_recall`) — a reinstalação acidental só atualizou essa cópia pro código atual deste repo, sem quebrar `total-recall-codex --help` nem os imports
    - **Onde**: nenhum código do projeto alterado — registrado aqui pra não repetir o diagnóstico do zero numa próxima sessão que precise reinstalar nesse venv específico
