# Handoff — Advisor tool, FastContext e melhorias no /recall (2026-07-05 → 2026-07-06)

**Branch:** `vingador-do-sonnet` — 2 commits ahead de `origin/vingador-do-sonnet`, **sem push**
**Working tree:** limpo (`git status` confirmado em 2026-07-06)
**Modelo usado na sessão:** Fable 5 (orquestração) + sub-agentes Sonnet e Haiku (execução delegada)

Este handoff é detalhado de propósito — cobre o raciocínio, não só o resultado, para
que quem retomar não precise re-derivar as decisões.

---

## 1. Ponto de partida da sessão

O usuário pediu para avaliar duas referências como possível melhoria para as skills
`/recall` e `/maestro`:

1. **[Advisor tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool)**
   (Anthropic, beta `advisor-tool-2026-03-01`) — server tool da Messages API onde um
   modelo executor barato consulta um modelo mais forte mid-generation.
2. **[FastContext](https://arxiv.org/html/2606.14066v1)** (Microsoft, arXiv 2606.14066)
   — paper sobre treinar um subagente explorador de repositórios (Qwen3-4B/30B via
   SFT+RL) que devolve só contexto focado (paths + line ranges) ao agente principal,
   reduzindo tokens e melhorando acurácia end-to-end.

O tema comum, nomeado pelo usuário: usar **modelo mais fraco (ou local) para tarefas
braçais**, reservando modelo forte para julgamento. Essa é a lente com que as duas
referências foram avaliadas.

## 2. Veredicto de cada referência

### 2.1 Advisor tool — não aplicável dentro de skills
- É recurso da **Messages API**; skills do Claude Code não controlam o array `tools`
  de uma chamada de API — não há como "ligar" o advisor de dentro de uma skill.
- Único candidato natural no ecossistema seria o `brainiac` (`llm_synth.py`, invoca
  Haiku) — mas ele usa `claude -p` via subprocess por decisão deliberada (D-LLM-2:
  "sem dependência Python externa, nada importa anthropic/openai"). Adotar o advisor
  ali exigiria migrar para o SDK, revogando essa decisão por um ganho pequeno. **Não
  fizemos isso.**
- **O que foi de fato aproveitado:** só os padrões de prompt da documentação do
  advisor, que são agnósticos de onde rodam:
  - Reconciliação nomeada de conflito ("X vs Y — qual evidência desempata?")
  - Cap de output em sub-agente (evita síntese longa demais)
  - Padrão "coletor barato + julgador forte" (o próprio /recall já ia nessa direção;
    reforçamos)

### 2.2 FastContext — validou a arquitetura já existente + achado prático
- Confirma que a arquitetura do /recall (busca delegada a sub-agente, orquestrador só
  recebe a síntese) está na direção certa — é o mesmo desenho do paper.
- Achado prático descoberto **durante** a sessão (não estava no plano original): os
  modelos treinados foram **publicados no Hugging Face**:
  - `microsoft/FastContext-1.0-4B-SFT` e `microsoft/FastContext-1.0-4B-RL` (MIT)
  - GGUFs prontos para Ollama (`mitkox/FastContext-1.0-4B-RL-Q4_K_M-GGUF`, etc.)
  - Repo: https://github.com/microsoft/fastcontext
- **Limitação clara:** treinado para explorar código (Read/Glob/Grep em repos), não
  transcripts de conversa — não substitui o motor do total-recall. Virou sidequest
  separada (ver §7).

## 3. Mudança de código no total-recall

### 3.1 `--format pointers` (commit `2e9b2a9`)
Arquivos: `src/total_recall/models.py` (`RecallContext.format_pointers`),
`src/total_recall/cli.py` (novo choice no `--format`).

**Importante — isto passou por uma correção de rumo dentro da própria sessão:**
- **Primeira versão** (proposta e até implementada inicialmente): citar na íntegra
  só os top-3 hits por rank, resto vira ponteiro de 1 linha. Raciocínio inicial: "lição
  do FastContext, evidência se concentra no topo".
- **O usuário contestou** essa mudança antes de aceitar ("algumas parecem regressões,
  tô preocupado de não ter entendido a dimensão do que vc decidiu por mim") e pediu um
  **estudo empírico com dados reais de uso** antes de aplicar qualquer coisa.
- **Estudo rodado** (sub-agente Sonnet, ver §4) **refutou a hipótese top-3**: em 3 de 5
  buscas reais, havia evidência não-redundante nos ranks 4–8 (num caso, o alerta mais
  crítico estava no rank 8).
- **Versão final implementada:** `format_pointers(max_full_sessions=4)` — cita na
  íntegra o **melhor hit de cada sessão distinta** (até 4 sessões), não por posição
  de rank. Hits repetidos de sessão já citada, ou sessões além do teto, viram ponteiro
  de 1 linha (`session_id`, data, score, preview). Ponteiros marcam explicitamente
  `(sessão já citada)` quando aplicável.
- 17 testes passando após a mudança (`pytest tests/ -q`).

**Lição que fica para sempre:** o preditor de utilidade nos resultados do total-recall
é **sessão ainda não representada no conjunto já citado**, não o rank/score. Qualquer
mudança futura no formato de saída deve respeitar isso.

### 3.2 Uso pretendido do `--format pointers`
Pensado para quando o **consumidor da saída é outro agente com contexto apertado**
(ex.: camada 2 do /maestro), não para a síntese final do /recall entregue ao usuário
— essa continua sendo texto livre sintetizado pelo sub-agente. **Não foi aplicado
ao /maestro nesta sessão** (usuário pediu mudança mínima lá — só a reconciliação
nomeada, ver §5.2). Fica no backlog (§6) para reavaliar depois que o formato provar
valor em uso real no /recall.

## 4. Estudo empírico — metodologia e achados completos

Sub-agente Sonnet (`model: "sonnet"`) recebeu esta tarefa: extrair as 5 últimas
buscas reais de `total-recall search` dos transcripts JSONL (via grep nos
`~/.claude/projects/*/*.jsonl`, ordenado por recência, descartando testes óbvios do
dia), re-executar cada uma com `--format json --limit 8`, e analisar rank por rank
se a evidência útil se concentra no topo.

**5 queries reais analisadas:** `router v2 col16 col18 pente fino`, `Fable 5 tarefa
complexa`, `final da sessão, onde paramos` (com `--session`), `saneamento aste absa
D-25`, `vingador`.

**Achados:**
1. **Hipótese "top-3 basta" falhou em 3/5 queries.** Evidência nova apareceu nos
   ranks 4–8 — ex.: em `saneamento aste absa D-25`, o alerta "isso é resíduo lateral
   de um teste, não trabalho real" só aparecia no **rank 8**.
2. **Ruído e substância vêm intercalados, não segregados por posição.** Na mesma
   query, ranks 1/3/5/7 eram eco de comando/meta enquanto 2/4/6/8 tinham conteúdo real
   — corte por rank fixo mantém ruído e descarta substância ao mesmo tempo.
3. **Auto-contaminação do índice descoberta aqui.** Sessões anteriores que rodaram o
   próprio `/recall` foram indexadas como conteúdo — o comando ecoado, "busca
   disparada em segundo plano", task-notifications — e isso infla ruído e rankeia
   alto. **Este é o achado mais sério do estudo** (ver §6, item 1 do backlog).
4. **`--session` é o mecanismo de foco mais eficaz.** Quando usado, o resultado
   colapsa naturalmente para 1 sessão e top-3 already basta com folga.
5. **Teto de 300 palavras: ganho em 4/5 queries**, só ficou justo (~400) no caso com
   4 sessões distintas carregando fatos não-redundantes — daí o teto flexível
   300/450 na versão final da skill.
6. **`--limit 8` confirmado correto** — `--limit 5` teria cortado evidência real em
   2/5 queries.

## 5. Skills atualizadas (vivem em `~/.claude/skills/`, fora deste repo)

### 5.1 `/recall` — reescrita completa
Arquivo: `~/.claude/skills/recall/SKILL.md`. Mudanças:
- **Passo 0 novo, visível ao usuário:** antes de delegar a busca, checar se a
  resposta já está no contexto da conversa ou é trivialmente verificável (git log,
  arquivo, APRENDIZADOS.md). Se sim, perguntar: *"já há evidência disso aqui: [fonte].
  Rodo o /recall mesmo assim?"* — só prossegue sem perguntar se o usuário já invocou
  `/recall` explicitamente com query clara sobre sessões passadas.
- **Sub-agente: Sonnet → Haiku com fallback Sonnet.** Retry único e avisado ao
  usuário se a síntese vier claramente degradada (não responde à pergunta, cita eco
  de comando como evidência, ignora contradição óbvia). Critério de rollback (para
  quem observar isso nas próximas semanas): fallback disparando em >1/3 das buscas,
  ou usuário notando sínteses piores → voltar default para Sonnet.
- **Síntese por sessão distinta**, não por rank (aplicando o achado do estudo).
- **Descarte explícito de hits eco/meta** no prompt do sub-agente (mitigação
  provisória para a auto-contaminação do índice — o fix definitivo é no parser,
  ver §6).
- **Contradições entre sessões nomeadas explicitamente**, nunca resolvidas
  silenciosamente pela sessão "mais confiante".
- **Buscas paralelas** com 1-2 variantes da query (sinônimos, abreviação, PT/EN).
- **Tamanho: alvo ~300 palavras, extensão até ~450** se >3 sessões distintas com
  fatos novos.
- **Nota sobre `--format pointers`**: mencionada como opção para quando o consumidor
  é outro agente, não para a síntese ao usuário.

### 5.2 `/maestro` — mudança mínima e cirúrgica
Arquivo: `~/.claude/skills/maestro/SKILL.md`. O usuário pediu explicitamente **só**
esta mudança (rejeitou aplicar o padrão coletor-barato/julgador-forte lá nesta
rodada):
- **Reconciliação nomeada de conflito** adicionada à seção "Reconciliação — git é o
  juiz": ao detectar conflito narrativa×fatos, formular explicitamente "a sessão narra
  X, mas a camada 1 mostra Y — qual evidência verificável desempata?". Resolver
  **sempre** por evidência citável (hash de commit, `[x]` no tasks.md, run_id) —
  nunca pela narrativa que parece mais confiante. Sem desempate, o item entra no
  sumário como **conflito explícito**, não como resolvido.

## 6. Bug de deploy corrigido (achado no meio do caminho, não estava no escopo original)

Ao tentar testar `--format pointers` pela primeira vez, o CLI não reconhecia a opção
mesmo após editar o código. Investigação revelou:
- `~/.venvs/total-recall-py312/bin/pip` **apontava para o venv errado** — na verdade
  resolvia para `~/.venvs/total-recall-codex-py312/lib/.../site-packages` (o do
  projeto `total-recall-codex`, não o do `total-recall`).
- A cópia de deploy real fica em `~/.local/share/total-recall-app/` (instalada a
  partir daí, não do repo em `Desktop/Projetos-IA/total-recall/`).
- Havia também um `build/lib/` obsoleto dentro dessa cópia de deploy, interferindo na
  reinstalação.
- **Sintoma:** o binário instalado estava **congelado desde 16 de maio de 2026** —
  nenhuma mudança de código no repo chegava ao CLI usado no dia a dia, silenciosamente,
  há quase dois meses.

**Fluxo de deploy correto (documentado para não se perder de novo):**
```bash
rsync -a --delete /Users/criacao/Desktop/Projetos-IA/total-recall/src/ \
  /Users/criacao/.local/share/total-recall-app/src/
/Users/criacao/.venvs/total-recall-py312/bin/python -m pip install \
  --no-cache-dir --force-reinstall --no-deps \
  /Users/criacao/.local/share/total-recall-app
```
Usar sempre `python -m pip` (não o `pip` do PATH do venv, que pode resolver errado) e
`--no-cache-dir` (o pip cacheia wheels e pode servir uma versão antiga sem isso).

**Faxina feita:** removidos `~/.local/share/total-recall-app/build/` e
`.../src/total_recall.egg-info/` (artefatos de empacotamento, contribuíam para o
problema, seguros de remover).

## 7. Commits desta sessão (branch `vingador-do-sonnet`, sem push)

```
9dde03c docs: plano advisor/fastcontext, backlog de próximas sessões e aprendizados 23-27
  APRENDIZADOS.md (+35 linhas, itens 23-27)
  BRAINIAC_DIGEST.md (+26/-2, nova seção "Sessão 2026-07-05 (Fable 5)")
  docs/BACKLOG-PROXIMAS-SESSOES.md (novo, 44 linhas)
  docs/PLANO-ADVISOR-FASTCONTEXT-2026-07-05.md (novo, 110 linhas)

2e9b2a9 feat(recall): --format pointers com dedupe por sessão (estudo empírico 2026-07-05)
  src/total_recall/cli.py (+7/-1)
  src/total_recall/models.py (+69 linhas, format_pointers)
```

Ambos criados por um sub-agente Sonnet dedicado a "arrumar a casa" (testes verdes
confirmados antes de cada commit; nenhum arquivo estranho no `git status`).

## 8. O que NÃO foi feito (decisão explícita, não esquecimento)

- **Filtro de auto-contaminação no `session_parser.py`** — identificado como o
  achado mais sério do estudo, mas não implementado nesta sessão. É o item #1 do
  backlog (§9). A mitigação atual é só uma regra no prompt do sub-agente do /recall
  ("descarte hits que são eco/meta"), que reduz o sintoma mas não a causa.
- **`--format pointers` no /maestro** — usuário optou por não mexer no /maestro além
  da reconciliação nomeada. Reavaliar depois que `pointers` provar valor no /recall.
- **Merge da branch `vingador-do-sonnet` para `main`** — fica a critério do usuário,
  não decidido nesta sessão.
- **Migração do brainiac para SDK (pré-requisito do Advisor tool)** — fora de escopo,
  só registrado como condição futura.

## 9. Backlog (fonte completa: `docs/BACKLOG-PROXIMAS-SESSOES.md`)

Resumo dos 3 horizontes (ver o arquivo para os detalhes de cada item):
- **Agora (próxima sessão):** filtro de auto-contaminação do índice + decisão sobre
  merge da branch.
- **Observação contínua (~2 semanas):** avaliar taxa de fallback Haiku→Sonnet no
  /recall; registrar ocorrências no APRENDIZADOS.md.
- **Explorações:** FastContext-4B como explorador de código (ver §10 — já iniciado
  como sidequest, com achado sério pendente de resolver antes de integrar);
  `--format pointers` no /maestro; Advisor tool condicionado à migração do brainiac.

## 10. Sidequest paralela: FastContext local via Ollama

Fora do escopo deste repo — vive em `/Users/criacao/Desktop/Projetos-IA/fastcontext-explorer/`
(diretório próprio, não dentro do total-recall — correção explícita do usuário,
registrada como memória persistente). Resumo do estado: harness funcional, 2 testes
rodados contra este repo (só leitura), achado sério de alucinação de resposta de tool
(o modelo simulou uma saída de `Grep` inteira em vez de aguardar execução real). Ver
`fastcontext-explorer/HANDOFF.md` para o handoff completo daquela linha de trabalho —
não duplicado aqui de propósito.

## 11. Memórias persistentes criadas nesta sessão (Claude Code memory store)

Para quem retomar entender por que o comportamento do assistente muda:
- `modelo-fraco-para-trabalho-bracal.md` (tipo `user`) — preferência por modelo
  fraco/local em tarefa braçal, forte para julgamento.
- `mudancas-de-skill-exigem-evidencia.md` (tipo `feedback`) — não aplicar mudança de
  comportamento em skill sem propor riscos em PT-BR e (quando testável) rodar estudo
  empírico antes.
- `fastcontext-diretorio-proprio.md` (tipo `feedback`) — FastContext vive em projeto
  próprio, nunca dentro do total-recall.

## 12. Para retomar rapidamente

1. `git -C /Users/criacao/Desktop/Projetos-IA/total-recall log --oneline -5` — confirma
   que os 2 commits desta sessão ainda estão lá e a branch é `vingador-do-sonnet`.
2. Ler `docs/BACKLOG-PROXIMAS-SESSOES.md` para o próximo passo priorizado (filtro de
   auto-contaminação).
3. Se for mexer no `/recall` de novo, ler `~/.claude/skills/recall/SKILL.md` inteiro
   primeiro — ele já incorpora todo o raciocínio deste handoff.
4. Se for continuar a sidequest do FastContext, ir direto para
   `fastcontext-explorer/HANDOFF.md` (não este arquivo).
