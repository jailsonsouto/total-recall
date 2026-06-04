# Análise comparativa: memória do brainiac (autoresearch) × Anton (Cortex)

> Relatório analítico produzido em 2026-06-04.
> Compara o modelo de memória do **brainiac**
> ([`jailsonsouto/autoresearch-brainiac`](https://github.com/jailsonsouto/autoresearch-brainiac))
> com o mecanismo de memória do agente **Anton** (`mindsdb/anton`, módulo
> `anton/core/memory/`). Responde diretamente: **como o brainiac se beneficiaria de
> `anton/core/memory/`?**

---

## Contexto dos três sistemas

Esta é a terceira peça de uma análise que já cobriu Total Recall e Anton. Os três
ocupam pontos distintos no espaço de "memória de agente":

| Sistema | Tipo de memória | Pergunta que responde |
|---|---|---|
| **Total Recall** | episódica (índice semântico passivo de conversas) | *"O que foi dito, lá atrás, sobre X?"* |
| **Anton / Cortex** | declarativa/procedural **curada** (rules, lessons, identity) | *"Quem sou, o que aprendi, como me comportar agora?"* |
| **brainiac / autoresearch** | experimental procedural (ledger git + TSV) | *"O que eu já tentei e o que funcionou?"* |

Total Recall é **passivo** (não age). Anton e brainiac são ambos **memória de agente
ativa** — mas em eixos opostos, e é por isso que a comparação entre eles é a mais
rica.

---

## O modelo de memória do brainiac: "git is memory"

brainiac é um port da metodologia *autoresearch* do Karpathy. A memória **é o próprio
repositório git**:

- **Experimentos são commits** com prefixo `experiment:`. Cada iteração produz um
  commit *antes* da verificação.
- **Falhas são preservadas**: quando a métrica piora, `git revert` desfaz a mudança
  mas mantém o experimento no histórico (`git revert` em vez de edição destrutiva).
- **`results.tsv`** registra cada iteração: `iteração | hash do commit | métrica |
  delta | status (baseline/keep/discard) | descrição`.
- **Regra de ouro**: o agente **relê `git log` + `git diff` + `results.tsv` antes de
  cada iteração** — *read before write*. É assim que ele "lembra" o que já tentou.
- **Relatórios datados**: `security/{date}-{slug}/`, `reason/{date}-{slug}/`,
  `probe/{date}-{slug}/`, com `lineage.md`, `candidates.md`, `judge-transcripts.md`,
  TSVs e `handoff.json` (encadeamento entre comandos).
- **Hipóteses falsificáveis** (confirmed/disproven/inconclusive): hipóteses
  *disproven* são logadas — valiosas para não repetir abordagens.
- **Sem embeddings, sem vetor, sem banco.** Memória = ledger versionado +
  verificação mecânica. Mantém só o que comprovadamente melhora a métrica.

O loop: *revisar estado + git history + results → escolher UMA mudança → commit →
verificar métrica → keep ou `git revert` → logar no TSV → repetir.*

---

## Comparação eixo a eixo

| Eixo | brainiac (autoresearch) | Anton (Cortex) |
|---|---|---|
| **Substrato** | commits git + `results.tsv` + relatórios datados | engrams markdown (`profile/rules/lessons/topics.md`) |
| **Unidade** | linha de TSV + commit `experiment:` | `Engram` (text/kind/scope/confidence/topic/source/id) |
| **Recall** | **replay total** de `git log`+TSV a cada iteração | Cortex **seleciona** o relevante (cue-dependent via LLM) |
| **Destilação** | **nenhuma** — guarda registros crus, re-deriva a lição relendo | Consolidator extrai **lições duráveis** (sleep replay) |
| **Gate de escrita** | **verificação mecânica** — só mantém se a métrica melhora | `encoding_gate` por confiança/modo (autopilot/copilot/off) |
| **Escopo** | preso a **um repo** (git local), não transfere entre tarefas | **global + project**, cross-sessão |
| **Erros** | `git revert` + hipóteses *disproven* logadas (registro) | Consolidator/Cerebellum aprendem **padrões** de erro |
| **Auditabilidade** | **total e reversível por design** (cada mutação é um commit) | stores markdown mutáveis com lock `fcntl` |
| **Aprende com uso?** | acumula histórico, mas não comprime | consolida, reforça, deduplica (vacuum) |

A leitura essencial: **brainiac e Anton são quase imagens espelhadas.** brainiac tem um
*substrato de memória impecável* (auditável, reversível, verificado mecanicamente) mas
**não destila nem recupera seletivamente** — depende de o agente reler o ledger inteiro.
Anton tem exatamente o que falta ao brainiac: *destilação* (Consolidator) e
*recuperação seletiva* (Cortex) — mas sobre um substrato mais frágil (markdown mutável,
gate só heurístico).

---

## Como o brainiac se beneficiaria de `anton/core/memory/`

Em ordem de impacto:

### 1. Consolidator (o maior ganho)
Hoje o brainiac **relê o ledger inteiro a cada iteração**. Com 89, 700, milhares de
experimentos, isso não escala — e o sinal útil dilui no ruído. Um passo de
consolidação, análogo ao `replay_and_extract()` do Anton, rodaria a cada N iterações
e **destilaria o TSV em poucas lições/regras duráveis**:

- *"never aumentar LR acima de X neste dataset — experimentos #12, #27, #41 todos
  regrediram"*
- *"always rodar os edge-cases de auth primeiro — pegam 3 das 5 regressões"*

Em vez de reprocessar 700 linhas, o agente carrega 8 lições de alto sinal. É a ponte
entre "tentei tudo" e "sei o que importa".

### 2. Cortex — recuperação cue-dependent
Quando o ledger cresce, alimentar todo o `git log`+TSV estoura o orçamento de contexto.
Um retriever ao estilo `_retrieve_relevant_rules()` **selecionaria só os experimentos
relevantes à hipótese atual** (mesmo bairro do espaço de busca), em vez de replay
total. Hoje brainiac faz "full replay"; o Cortex faz "carrega o que importa agora".

### 3. Hippocampus rules (Always/Never/When)
As "critical rules" do brainiac (one change/iteration, mechanical verification only,
revert on failure) são **hardcoded na skill**. Convertê-las em *engrams aprendidos* —
e deixar o brainiac **acumular regras específicas do projeto** entre runs
("Never tocar no arquivo X", "When a métrica estagna, tente a família Y") — daria
memória comportamental persistente, hoje inexistente.

### 4. Escopo global (cross-tarefa)
A memória do brainiac **morre com o repo**: lições de uma pesquisa não transferem para
outra. Um Hippocampus **global** (separado do project, como no Anton) deixaria
aprendizados de domínio ("como otimizar transformers", "armadilhas de tuning de
RAG") viajarem entre repositórios e tarefas.

### 5. Cerebellum — aprendizado supervisionado de erro
brainiac **reverte** falhas, mas não constrói um *modelo* de erro. Um Cerebellum
preveria **classes de experimento que tendem a crashar** e as pularia antes de gastar
uma iteração — transformando reversões reativas em prevenção.

### 6. ACC — detecção de padrão de turno
O córtex cingulado anterior do Anton detecta repetição/loop. Aplicado ao brainiac,
**evitaria re-tentar hipóteses já marcadas como *disproven*** — fechando o vazamento
de relê-mas-não-aprende.

---

## Simetria: o que o Anton roubaria do brainiac

A troca não é de mão única. O brainiac tem duas coisas que **fortaleceriam o Anton**:

1. **"Git is memory" → auditabilidade e reversibilidade total.** Os stores do Anton
   são markdown mutável com lock `fcntl`; uma mutação errada de memória é difícil de
   rastrear ou desfazer. Memória *backed by git* daria ao Anton time-travel e auditoria
   de cada engram.
2. **Gate de verificação mecânica.** O `encoding_gate` do Anton decide por *confiança*
   (heurística). O brainiac só memoriza o que **comprovadamente melhora uma métrica** —
   um critério muito mais rigoroso. Anton poderia exigir evidência mecânica antes de
   promover certos engrams a alta confiança.

---

## Veredito

O encaixe é quase perfeito porque os dois sistemas são **complementares por
construção**:

> brainiac tem o **substrato** (ledger git auditável) e o **gate** (verificação
> mecânica) que o Anton não tem.
> Anton tem a **destilação** (Consolidator) e a **recuperação seletiva** (Cortex) que o
> brainiac não tem.

A evolução lógica do brainiac não é trocar o git por um banco vetorial — é **manter o
git como substrato e adicionar uma camada cognitiva por cima**: um Consolidator que
comprime o ledger em lições, e um Cortex que recupera só o relevante para a iteração
atual. O git continua sendo a verdade auditável; o Cortex/Consolidator viram a
*memória de trabalho* sobre essa verdade.

---

## Fontes

- [`jailsonsouto/autoresearch-brainiac`](https://github.com/jailsonsouto/autoresearch-brainiac)
  — `README.md`, `plugins/autoresearch/.../references/core-loop.md` (branch `master`).
- [`mindsdb/anton`](https://github.com/mindsdb/anton) — `anton/core/memory/`
  (`cortex.py`, `hippocampus.py`, `consolidator.py`, `cerebellum.py`, `acc.py`,
  `base.py`).
- Metodologia autoresearch do Karpathy ("git is memory", loop de experimentos, TSV de
  resultados).
- Relatório irmão: `docs/ANALISE-MEMORIA-ANTON-CORTEX-VS-TOTAL-RECALL.md`.

---

## Registro como artefato brainiac (passo local)

A skill `/brainiac` não existe neste ambiente remoto (container só com o repo
total-recall). Para registrar estes dois relatórios como artefatos do brainiac na sua
máquina, copie os arquivos para o projeto brainiac e rode a skill:

```bash
# na máquina local, dentro do projeto brainiac
cp <caminho>/total-recall/docs/ANALISE-MEMORIA-ANTON-CORTEX-VS-TOTAL-RECALL.md  ./
cp <caminho>/total-recall/docs/ANALISE-MEMORIA-BRAINIAC-VS-ANTON.md            ./
/brainiac   # registrar os artefatos conforme a convenção da skill
```
