# Memória Viva — Agente 8 (Memory Manager)

Sistema de memória persistente para o framework multi-agente de briefing de produto Novex/Embelleze.
Transforma o sistema de "ferramenta que responde" em "sistema que aprende".

## O problema que resolve

Sem memória, cada briefing começa do zero:
- O Comitê rejeita um briefing. Na semana seguinte, ideia similar é submetida. O sistema não sabe.
- BVS Preditivo: 8.2. BVS Real (6 meses depois): 7.1. O sistema nunca se recalibra.
- Agente 4 analisa 600 comentários. Duas semanas depois, reanálise do zero.

Com a Memória Viva, o sistema **aprende a cada briefing**.

## Instalação rápida

```bash
# Pré-requisito: Ollama instalado e rodando
ollama pull nomic-embed-text

# Instalar
cd projetos/memoria-viva
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Inicializar
cp .env.example .env
memoria-viva init
```

Ver [INSTALL.md](INSTALL.md) para o guia completo passo-a-passo.

## Arquitetura

3 camadas de memória em um único arquivo SQLite:

```
novex-memory.db
├── briefing_threads      ← Hot Store: estado dos briefings, scores, decisões
├── score_calibrations    ← Hot Store: calibrações Bayesianas do BVS
├── memory_patterns       ← Hot Store: padrões de aprovação/rejeição
├── chunks + chunks_vec   ← Warm Store: vetores para busca semântica
└── chunks_fts            ← Warm Store: índice para busca por keyword

cold_store/
├── BRAND_MEMORY.md       ← Código Genético (sempre injetado)
├── MEMORY.md             ← Insights consolidados
└── briefings/            ← Logs diários
```

## Os 4 momentos do Agente 8

| Momento | Quando | O que faz |
|---|---|---|
| 1 — Memory Read | Antes de rodar os agentes | Injeta contexto histórico |
| 2 — Post-briefing Flush | Após o briefing terminar | Salva o que vale lembrar |
| 3 — Committee Flush | Quando o Comitê decide | Extrai padrões, calibra BVS |
| 4 — Manutenção | Cron semanal | Aging, compaction, backup |

## Comandos CLI

```bash
memoria-viva init                              # Inicializa
memoria-viva status                            # Estado da memória
memoria-viva memory-read "sérum de transição"  # Testa o Memory Read
memoria-viva search "transição capilar"        # Busca na memória
memoria-viva briefings                         # Lista briefings
memoria-viva flush <id> GO -r "ativo validado" # Committee Flush manual
memoria-viva bvs-real <id> 85.0               # Insere BVS Real
```

## Stack técnica

| Componente | Tecnologia | Motivo |
|---|---|---|
| Banco de dados | SQLite (WAL mode) | Zero servidor, transações atômicas |
| Busca vetorial | sqlite-vec | Mesmo arquivo do banco, O(n) < 5ms |
| Busca textual | FTS5 (built-in) | Sem dependências extras |
| Embedding | nomic-embed-text via Ollama | Local, gratuito, dados não saem |
| Embedding (alt.) | OpenAI text-embedding-3-small | Trocar no `.env` |
| Trigger Comitê | Basecamp polling 15min | Sem URL pública necessária |

## Documentação

| Documento | Conteúdo |
|---|---|
| [docs/PRD.md](docs/PRD.md) | Requisitos e métricas de sucesso |
| [docs/ARQUITETURA.md](docs/ARQUITETURA.md) | Arquitetura técnica detalhada |
| [docs/ADRs.md](docs/ADRs.md) | 7 decisões de arquitetura registradas |
| [docs/GLOSSARIO.md](docs/GLOSSARIO.md) | Termos do domínio |
| [ROADMAP.md](ROADMAP.md) | 4 estágios de maturidade |
| [INSTALL.md](INSTALL.md) | Guia de instalação passo-a-passo |

## Estágios de maturidade

| Estágio | Descrição | Status |
|---|---|---|
| 1 — Amnésica | Sem memória (estado anterior) | — |
| 2 — Episódica | Hot Store + flushes básicos | **MVP implementado** |
| 3 — Semântica | Calibração Bayesiana + integração Agentes 2/4/5 | A implementar |
| 4 — Estratégica | TD Learning + pattern detection | A implementar |

---

Planejado na sessão Claude + Jay de Março/2026.
Ver [notas/](../../notas/) para transcrições completas das sessões.
