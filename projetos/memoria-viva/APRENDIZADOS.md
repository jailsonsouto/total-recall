# Aprendizados — Memória Viva

> **Para o Claude:** ao iniciar uma sessão neste projeto, leia este arquivo antes de qualquer ação.
> Ele registra raciocínios críticos, erros evitados e decisões não óbvias que não aparecem no código.

---

## Como ler este arquivo

Cada entrada tem:
- **O que foi descoberto** — o fato técnico ou decisão
- **Por que importa** — o que teria quebrado ou custado sem esse conhecimento
- **Onde está no código** — localização para referência rápida

---

## Sessão — Março/2026: planejamento e decisões de arquitetura

### 1. SQLite unificado em vez de múltiplos backends

**Decisão:** usar um único arquivo SQLite com extensões (sqlite-vec para vetorial, FTS5 para keyword) em vez de SQLite + ChromaDB separados.

**Por que importa:** ChromaDB exige servidor ou processo separado. No contexto de briefing (roda no Mac do PM), servidor adicional é atrito. SQLite é um arquivo — sem deployment, sem configuração, zero custo operacional. sqlite-vec entrega busca vetorial sem sair do SQLite.

**Trade-off registrado:** sqlite-vec não tem os recursos avançados do ChromaDB (HNSW tuning, coleções nomeadas). Para o volume atual (< 100k memórias), sqlite-vec é suficiente.

**Onde está:** `docs/ADRs.md` — ADR sobre persistência, `docs/ARQUITETURA.md` — Hot/Warm Store

---

### 2. Committee Flush nunca pode falhar — write-ahead antes de confirmar

**Decisão:** o Committee Memory Flush (momento em que o Comitê aprova/rejeita um briefing) é o dado mais valioso do sistema — o sinal de ground truth que calibra o BVS.

Implementar com **write-ahead**: salva no Cold Store (filesystem Markdown + Git) antes de confirmar no Warm Store. Se o processo cair no meio, o dado está no arquivo. Se o arquivo existir mas o Warm Store não tiver, reprocessa na inicialização.

**Por que importa:** perder um Committee Flush é perder um ponto de dados raro e insubstituível. Diferente de briefings (gerados frequentemente), o Comitê se reúne poucas vezes por mês.

**Onde está:** `docs/ARQUITETURA.md` — momento 3 (Committee Memory Flush)

---

### 3. nomic-embed-text via Ollama — não API de embeddings

**Decisão:** usar `nomic-embed-text` local via Ollama para embeddings, não a API de embeddings da Anthropic ou OpenAI.

**Por que importa:** embeddings são chamados em todo briefing, múltiplas vezes. Custo por chamada × volume = custo operacional real. Ollama local = custo zero. `nomic-embed-text` (768 dims) é comparável a text-embedding-3-small em benchmarks de recuperação semântica.

**Requisito:** Ollama precisa estar rodando localmente. Documentado em `INSTALL.md`.

**Onde está:** `docs/ADRs.md`, `INSTALL.md`

---

### 4. Cold Store é Markdown + Git — legível por humanos é requisito

**Decisão:** o Cold Store (histórico de briefings, padrões de longo prazo) usa arquivos Markdown versionados por Git, não banco de dados.

**Por que importa:** o PM precisa conseguir abrir o Cold Store num editor de texto e entender o que está lá. Se o sistema de IA falhar, o conhecimento não pode estar preso num formato binário. Git também resolve backup, auditoria e diff automático.

**Onde está:** `cold_store/BRAND_MEMORY.md`, `cold_store/PM_CONTEXT.md`, `cold_store/MEMORY.md`

---

### 5. LangGraph State como Hot Store — não banco separado

**Decisão:** o estado do briefing em andamento (Hot Store) vive no LangGraph State, não em banco adicional.

**Por que importa:** LangGraph já gerencia o estado do grafo. Adicionar banco para o Hot Store seria duplicar. O LangGraph SqliteSaver já persiste o estado entre nós — o Hot Store é literalmente o checkpoint do grafo.

**Onde está:** `docs/ARQUITETURA.md` — Hot Store

---

## Convenções deste projeto

- **Zero servidores em produção:** tudo roda local. Ollama para embeddings, SQLite para persistência, filesystem para Cold Store.
- **Committee Flush é sagrado:** nunca pode falhar, sempre write-ahead.
- **Cold Store é humano-legível:** Markdown, Git, editável sem ferramentas especiais.
- **4 momentos de operação fixos:** Memory Read → Post-briefing Flush → Committee Flush → Manutenção semanal. Não adicionar momentos sem ADR.
- **Integração com Vozes da Comunidade (Agente 4):** o Warm Store persiste padrões de consumer intelligence por (categoria, segmento HNR). Ver `docs/ARQUITETURA.md`.
