# Advisor tool + FastContext — avaliação, decisões e plano futuro

**Data:** 2026-07-05
**Contexto:** avaliação de duas referências para melhorar as skills /recall, /maestro e
correlatas: o [Advisor tool da Anthropic](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool)
e o paper [FastContext (Microsoft, arXiv 2606.14066)](https://arxiv.org/html/2606.14066v1).

---

## 1. Veredicto das referências

### Advisor tool (Anthropic, beta `advisor-tool-2026-03-01`)
- **Não se aplica diretamente às skills.** É um server tool da Messages API (executor
  barato consulta um modelo mais forte mid-generation). Skills do Claude Code não
  controlam o array de `tools` da API — não há como habilitá-lo de dentro do harness.
- **Único ponto de aplicação real no ecossistema:** o brainiac (`llm_synth.py`) invoca
  Haiku — mas via `claude -p` subprocess, decisão deliberada D-LLM-2 (sem SDK).
  Advisor exigiria migrar para o SDK + billing de API.
- **O que foi aproveitado (padrões de prompt, agnósticos de onde rodam):**
  - Reconciliação nomeada de conflito ("X vs Y — qual evidência desempata?") → aplicada
    no /maestro.
  - Cap suave de output no sub-agente → aplicado no /recall (alvo ~300/teto 450 palavras).
  - Padrão "coletor barato + julgador forte" (advisor invertido) → /recall usa Haiku
    para busca+síntese com fallback Sonnet; reconciliação do /maestro permanece no
    modelo principal.

### FastContext (Microsoft)
- **Arquitetura validada:** subagente explorador especializado que devolve só contexto
  focado (paths + line ranges) ao agente principal — mesmo desenho do /recall (busca
  delegada, orquestrador recebe só a síntese). Foco do paper era custo-efetividade:
  modelo 4B treinado supera/empata com modelos grandes na exploração (-14% a -60% de
  tokens, +3 a +5,5% de acurácia end-to-end).
- **Modelos publicados** (descoberto via HF em 2026-07-05):
  - `microsoft/FastContext-1.0-4B-SFT` e `microsoft/FastContext-1.0-4B-RL` (MIT, base Qwen3-4B)
  - GGUFs prontos p/ Ollama: `mradermacher/FastContext-1.0-4B-SFT-GGUF` (112K downloads),
    `mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF`, `sdougbrown/FastContext-1.0-4B-RL-GGUF`
  - Código: https://github.com/microsoft/fastcontext
- **Limitação:** treinado para explorar *repositórios de código* (Read/Glob/Grep),
  não transcripts de conversa. Não substitui o total-recall; serve como explorador de
  código local.

---

## 2. Decisões aplicadas (2026-07-05)

| # | Mudança | Onde | Status |
|---|---------|------|--------|
| 1 | `--format pointers` (dedupe por sessão: melhor hit de cada sessão distinta na íntegra, até 4; resto ponteiro) | `models.py::format_pointers`, `cli.py` | ✅ testado, 17 testes verdes |
| 2 | Sub-agente do /recall: Sonnet → **Haiku com fallback Sonnet** (retry único se síntese degradada) | `~/.claude/skills/recall/SKILL.md` | ✅ aplicado — **avaliar em uso real** |
| 3 | Buscas paralelas com 1-2 variantes da query no sub-agente | idem | ✅ |
| 4 | Síntese por sessão distinta (não por rank) + descarte de hits eco/meta + contradições nomeadas | idem | ✅ |
| 5 | Alvo ~300 palavras, extensão até 450 se >3 sessões com fatos novos | idem | ✅ |
| 6 | Anti-gatilho suave na description + **passo 0 de pré-cheque visível** ("já há evidência aqui: [fonte]. Rodo mesmo assim?") | idem | ✅ |
| 7 | Reconciliação nomeada de conflito narrativa×fatos | `~/.claude/skills/maestro/SKILL.md` | ✅ |
| 8 | Fix de deploy: pip do venv `total-recall-py312` apontava p/ venv do codex; binário instalado estava congelado em 16/maio | fluxo: rsync → `python -m pip install` da cópia `~/.local/share/total-recall-app` | ✅ |

## 3. Estudo empírico que corrigiu a hipótese (2026-07-05)

Sub-agente Sonnet re-executou as 5 últimas buscas reais (extraídas dos JSONL) com
`--format json --limit 8`. Resultados:

- **Hipótese "top-3 basta" FALHOU em 3/5 queries.** Evidência não-redundante apareceu
  nos ranks 4-8 (ex.: query `saneamento aste absa D-25` — o alerta crítico "isso é
  resíduo de teste, não trabalho real" estava no rank 8).
- **O preditor de utilidade é sessão nova, não rank.** Ruído e substância vêm
  intercalados; eco do próprio comando /recall rankeia alto.
- **`--limit 8` correto** — limit 5 cortaria evidência real em 2/5 queries.
- **Teto de 300 palavras: ganho em 4/5**; 1 caso multi-sessão precisou ~400 → daí o
  teto flexível 300/450.
- **`--session` é o melhor mecanismo de foco** — colapsa naturalmente o escopo.

## 4. Problemas descobertos (backlog priorizado)

### 4.1 Auto-contaminação do índice (prioridade ALTA)
Invocações anteriores do /recall (comando ecoado, "busca disparada em segundo plano",
task-notifications) estão indexadas como conteúdo e rankeiam alto nas buscas.
**Proposta:** filtro no `session_parser.py` — descartar/despriorizar chunks cujo
conteúdo case com padrões de eco (`total-recall search "`, `<task-notification>`,
marcadores de invocação de skill). Mitigação provisória: regra de descarte no prompt
do sub-agente (já aplicada).

### 4.2 Avaliação Haiku vs Sonnet no sub-agente (prioridade MÉDIA)
Critério de rollback: se em ~2 semanas de uso o fallback Sonnet disparar com
frequência (>1/3 das buscas) ou o usuário notar sínteses piores, voltar o default
para Sonnet. Registrar ocorrências no APRENDIZADOS.md.

### 4.3 Experimento FastContext local via Ollama (prioridade BAIXA/EXPLORATÓRIA)
- Puxar `FastContext-1.0-4B-SFT` GGUF Q4_K_M no Ollama (~2.5GB).
- Uso alvo: explorador de código barato/local nos projetos (não no total-recall).
- Harness necessário: as 3 tools read-only (Read/Glob/Grep) + parse do `<final_answer>`;
  o repo microsoft/fastcontext traz o formato de prompt.
- Ganho esperado: exploração de repo custo-zero para rondas do /maestro e pré-buscas.
- Riscos: modelo é EN-only nos exemplos; latência local; harness próprio a manter.

### 4.4 Advisor tool — condição de adoção futura
Só se/quando o brainiac migrar de `claude -p` para o SDK Anthropic (revogando D-LLM-2):
Haiku executor + Opus advisor na síntese, com `max_tokens: 2048` no advisor e caching
ephemeral se >3 consultas por conversa. Sem essa migração, não há superfície de uso.

### 4.5 `--format pointers` no /maestro (aguardando)
A camada 2 do /maestro pode usar `--format pointers` para poupar contexto na varredura
de sessões. Não aplicado nesta rodada (usuário optou por mudança mínima no maestro);
reavaliar após o /recall provar o formato em uso real.

## 5. Princípio consolidado

> **Modelo fraco/local para trabalho braçal (busca, coleta, exploração); modelo forte
> para julgamento (síntese complexa, reconciliação, decisão).** E: mudanças de
> comportamento em skills se decidem com evidência empírica de uso real, não com
> intuição de paper — a hipótese top-3 parecia óbvia e estava errada.
