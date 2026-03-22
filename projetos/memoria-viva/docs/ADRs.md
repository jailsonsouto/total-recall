# ADRs — Architecture Decision Records
## Memória Viva | Março 2026

---

### ADR-001: ChromaDB local para MVP (não Pinecone)

**Decisão:** Usar ChromaDB rodando localmente no MVP.

**Motivos:**
- Custo zero
- Latência local (sem round-trip de rede)
- Dados on-premise (nenhum dado de produto sai para cloud)
- Migration path trivial: `chroma.HttpClient(host="pinecone-endpoint")` quando necessário

**Trade-off aceito:** sem escalabilidade automática no MVP (aceitável para < 1.000 briefings/ano).

---

### ADR-002: SQLite com WAL mode para Hot Store

**Decisão:** SQLite com `PRAGMA journal_mode = WAL` como banco do Hot Store.

**Motivos:**
- Leituras concorrentes durante writes sem bloqueio
- Committee Memory Flush nunca pode ser perdido — WAL garante durabilidade mesmo em crash
- Zero configuração de servidor
- LangGraph SqliteSaver já usa SQLite nativamente

**Trade-off aceito:** não escala para múltiplos PMs simultâneos (sem problema no contexto atual — sistema é de uso individual).

---

### ADR-003: Markdown para Cold Store

**Decisão:** Filesystem com arquivos Markdown como camada Cold Store.

**Motivos:**
- Legível por humanos — PM pode editar `BRAND_MEMORY.md` diretamente
- LLM-friendly — Markdown é o formato nativo de contexto para modelos Claude
- Git = auditoria grátis (quem editou, quando, o quê)
- Validado em produção pelo OpenClaw e Nano-claw
- Zero custo operacional

**Trade-off aceito:** não permite buscas semânticas (para isso existe o Warm Store/ChromaDB).

---

### ADR-004: Claude Haiku para Agente 8 (exceto Committee Flush)

**Decisão:** Usar Claude Haiku para sínteses e extrações do Agente 8. Usar Claude Sonnet exclusivamente para o Committee Memory Flush.

**Motivos:**
- Haiku é 10-20x mais barato e suficiente para extração estruturada (flash pós-briefing, aging)
- Sonnet para Committee Flush: essa escrita é permanente, afeta todos os briefings futuros — vale o custo extra de qualidade
- Padrão análogo ao uso de modelos de embedding menores para indexação + modelos maiores para inferência

**Trade-off aceito:** maior latência no Committee Flush (~3-5s a mais). Aceitável — esse momento não é time-sensitive.

---

### ADR-005: OpenClaw como interface, não como substituto

**Decisão:** OpenClaw atua como gateway de interface multi-canal (WhatsApp/Telegram/Slack). LangGraph + CrewAI + ChromaDB resolvem a orquestração analítica.

**Motivos:**
- OpenClaw não tem RAG nativo
- OpenClaw executa agentes em sequência; o sistema requer paralelismo (Agentes 2, 3 e 4 paralelos → 90s vs 4-6min sequencial)
- LangGraph SqliteSaver provê replay de estado por checkpoint — OpenClaw não tem equivalente

**Arquitetura resultante:**
```
Jay (WhatsApp / Telegram / Slack)
          │
          ▼
    OpenClaw Gateway
    (interface + memória quente + workspace files)
          │
          ▼
    FastAPI Webhook
    (traduz mensagem → execução de workflow)
          │
          ▼
    LangGraph + CrewAI + ChromaDB
    (os 7+1 agentes de análise e memória)
          │
          ▼
    OpenClaw Gateway
    (entrega o briefing no canal preferido do PM)
```

**Trade-off aceito:** dois sistemas para manter em vez de um. Justificado pela diferença de capacidade analítica.
