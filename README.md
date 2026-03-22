# Agentes IA — Novex/Embelleze

Repositório central de agentes e projetos de IA desenvolvidos com Claude Code.
Sincronizado via OneDrive (Mac + Windows).

## Projetos

### [Memória Viva](projetos/memoria-viva/)
Agente 8 — Memory Manager do sistema multi-agente de briefing de produto.
Transforma o sistema de "ferramenta que responde" em "sistema que aprende".

**Status:** MVP implementado (Março 2026)
**Stack:** Python · SQLite · sqlite-vec · nomic-embed-text · Ollama

## Estrutura do repositório

```
agentes/
├── projetos/
│   └── memoria-viva/    ← Agente 8 (Memory Manager)
├── notas/               ← Sessões de planejamento e decisões de arquitetura
├── templates/           ← Templates reutilizáveis (a implementar)
└── CLAUDE.md            ← Contexto para o Claude Code
```

## Ambiente de desenvolvimento

- MacBook M1 (casa) + Windows 11 (trabalho)
- Claude Code como ambiente principal
- Python 3.11+, Ollama para modelos locais
