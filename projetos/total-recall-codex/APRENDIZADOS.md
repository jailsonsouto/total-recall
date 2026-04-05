# APRENDIZADOS — Total Recall Codex

> Documento vivo. Atualizar sempre que um aprendizado significativo surgir.

## 2026-04-05 — Criação do projeto

1. **Formato JSONL do Codex é fundamentalmente diferente do Claude Code**
   - Claude: `type` (system, user, assistant, progress) + `content` como array de blocos
   - Codex: `type` (session_meta, response_item, event_msg) + `payload.type` (message, agent_message, user_message, task_started, task_complete)
   - Codex é mais verboso mas mais estruturado — cada evento tem tipo explícito no payload

2. **Chunking turn-based vs exchange-based**
   - Claude: exchange = pergunta + resposta (baseado em sequência de mensagens)
   - Codex: turno = task_started → task_complete (baseado em ciclo de tarefa)
   - Turn-based é mais preciso: delimita naturalmente o escopo de cada interação

3. **Project label vem do conteúdo, não do path**
   - Claude: `~/.claude/projects/{project-dir}/session.jsonl` → project_label = project-dir
   - Codex: `~/.codex/sessions/YYYY/MM/DD/rollout-{ts}-{uuid}.jsonl` → project_label = session_meta.payload.cwd
   - Discovery precisa ler o início do JSONL para extrair o cwd

4. **Sem subagentes no Codex**
   - Codex não tem o conceito de subagentes observáveis do Claude Code
   - Simplifica: sem lógica de subagent, sem parent_session_id, sem is_subagent flag
   - INDEX_SUBAGENTS removido do config

5. **Graph Lite implementado desde o início**
   - Extração de entidades durante o parsing: backticks, ADR refs, ALL-CAPS terms, acronyms
   - Entidades armazenadas como metadata no chunk (JSON)
   - Futuro: tabela entities + chunk_entities para co-ocorrência e contradiction detection

6. **Skill do Codex usa formato diferente do Claude Code**
   - Claude: markdown puro com instruções
   - Codex: YAML frontmatter (name, description) + instructions markdown
   - Install path: `~/.codex/skills/recall/SKILL.md`

## 2026-04-05 — Melhorias V2 no mecanismo de busca

7. **Fuzzy threshold absoluto degrada com crescimento do corpus**
   - Threshold fixo `doc_count <= 10` funcionava com 3000 chunks mas falha com 284
   - Fix: threshold relativo `max(int(total_docs * 0.005), 3)` — 0.5% do vocabulário
   - Adicional: se token já existe no vocab com doc_count > 5, não expande
   - Para tokens ausentes (doc_count=0): exige score ≥ 90% no fuzzy match
   - Filtro extra: candidatos com doc_count > `token_doc_count * 3` são rejeitados
   - Resultado: "sqlite" parou de expandir para "site, slice, split"
   - **Onde**: `vector_store.py` (_fuzzy_find_variants, _build_fts_query)

8. **MMR não diversifica quando chunks da mesma sessão dominam**
   - Com corpus pequeno (8 sessões), MMR selecionava 2-3 chunks da mesma sessão
   - Fix: penalização de +0.3 na similaridade quando chunks compartilham session_id
   - Força o MMR a preferir chunks de sessões diferentes quando possível
   - Resultado: Query 3 agora retorna 3 sessões diferentes vs 2 antes
   - **Onde**: `recall_engine.py` (_mmr_rerank, loop de similaridade)

9. **Chunking turn-based do Codex gera chunks muito curtos**
   - Turns de 1-2 linhas (ex: "vc faria a mudança do banco de dados antes?")
   - Perde contexto e gera chunks semânticamente fracos
   - Fix: `_merge_short_turns()` merge chunks consecutivos do mesmo role até 200 chars
   - Resultado: 377 → 284 chunks (25% de redução, chunks mais densos)
   - **Onde**: `session_parser.py` (_merge_short_turns, chamado antes do chunking)

10. **Graph Lite implementado: entities + chunk_entities**
    - 2 tabelas novas no schema: `entities(id, name, type)` + `chunk_entities(chunk_id, entity_id)`
    - Extração durante indexação: backticks, ADR refs, CamelCase tech terms, acronyms
    - Noise filtering: path components (OneDrive, CloudStorage), stop acronyms (OK, NEU, PT, BR)
    - Graph boost na busca: +5% score para chunks que compartilham entidades com query terms
    - Entidades indexadas: ASTE (150 chunks), ABSA (142), API (138), LLM (113), JSON (118)
    - **Onde**: `database.py` (schema), `indexer.py` (_index_entities), `vector_store.py` (_apply_graph_boost)

11. **Python 3.13 não suporta sqlite3 extensions carregáveis**
    - `enable_load_extension` não existe no Python 3.13 do sistema
    - Necessário usar Python 3.12 do miniconda: `/Users/criacao/miniconda3/bin/python3.12`
    - **Onde**: `.venv` deve ser criado com Python 3.12

12. **Codex JSONL não tem timestamps nos payloads**
    - Apenas `session_meta` tem timestamp; eventos individuais não têm
    - Todos os chunks herdam o timestamp da sessão como fallback
    - Temporal decay funciona mas sem granularidade intra-sessão
    - **Onde**: `session_parser.py` (session_ts fallback)
