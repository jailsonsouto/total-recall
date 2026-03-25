# CLAUDE — Contexto do Projeto

## Sobre esta pasta
Repositório central de agentes e projetos de IA desenvolvidos com Claude Code.
Arquivos sincronizados via OneDrive (disponível no Mac e Windows).

## Estrutura
- `projetos/` — um subdiretório por projeto/agente
- `templates/` — templates reutilizáveis de agentes e prompts
- `notas/` — decisões de arquitetura, aprendizados, contexto geral

## Projetos ativos
- `projetos/memoria-viva/` — agente de memória viva (MVP implementado)
- `projetos/total-recall/` — memória pesquisável para sessões Claude Code
- `projetos/vozes-da-comunidade/` — ABSA/ASTE para análise de sentimento

## Total Recall — memória de longo prazo

O comando `total-recall` indexa TODAS as sessões passadas do Claude Code
e permite busca semântica + keyword. Está instalado em `~/.local/bin/total-recall`.

**Quando consultar:**
- Quando o usuário mencionar algo de uma sessão passada ("lembra quando...", "como fizemos...")
- Quando precisar de contexto histórico sobre uma decisão
- Quando iniciar trabalho num projeto que já foi discutido antes
- Quando o usuário usar `/recall`

**Como consultar:**
```bash
total-recall search "query aqui" --format context --limit 5
```

**Manter atualizado:** rodar `total-recall index` no início de sessões longas.

## Contexto de trabalho
- Desenvolvimento no MacBook M1 (casa) e Windows 11 (trabalho, OneDrive)
- Usar `CLAUDE.md` em cada subprojeto para contexto específico
- Git remote: https://github.com/jailsonsouto/agentes

## Convenções
- Commits frequentes com mensagens descritivas
- Cada projeto tem seu próprio `CLAUDE.md` com contexto específico
- Templates documentados em `templates/README.md`

## APRENDIZADOS.md — artefato obrigatório em todo projeto

**Todo projeto deve ter um `APRENDIZADOS.md` na raiz.**

Ao iniciar uma sessão em qualquer projeto: **leia o `APRENDIZADOS.md` antes de qualquer ação.**

O arquivo registra:
- Raciocínios críticos e decisões não óbvias que não aparecem no código
- Erros que seriam cometidos sem leitura prévia da documentação/código real
- Bugs evitados por pesquisa (ex: método errado, parâmetro obrigatório omitido)
- Convenções específicas do projeto

**Ao encerrar trabalho significativo em um projeto:** atualizar o `APRENDIZADOS.md` com o que foi descoberto na sessão.

Formato de cada entrada:
1. O que foi descoberto (fato técnico ou decisão)
2. Por que importa (o que teria quebrado)
3. Onde está no código (arquivo:linha ou seção)
