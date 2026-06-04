# Análise comparativa: memória do Anton (Cortex) × Total Recall

> Relatório analítico produzido em 2026-06-04.
> Compara o mecanismo de memória do agente **Anton** (`mindsdb/anton`, módulo
> `anton/core/memory/`) com o **Total Recall**.

---

## Esclarecimento de repositório

O mecanismo de memória conhecido como **Cortex** **não está** no `minds-platform`.
Ele vive no repositório do agente **Anton** (`mindsdb/anton`), em
`anton/core/memory/`. O `minds-platform` é a plataforma; o Anton é o "AI coworker"
cujo cérebro contém o Cortex. A arquitetura é explicitamente *brain-inspired*:
Cortex, Hippocampus, Consolidator, Cerebellum, ACC e Reconsolidator.

---

## TL;DR

São coisas de **categorias diferentes**, apesar de ambas se chamarem "memória":

- **Total Recall** é um **arquivo recuperável** — um sistema RAG passivo que indexa
  *tudo* e deixa você buscar depois. Não decide nada, não esquece nada, não destila
  nada.
- **Cortex** é um **gerente de memória ativo** — coordena, *decide o que carregar
  agora*, *destila experiência em lições*, *escreve memória nova de volta* e *injeta
  isso no system prompt* do agente a cada turno.

> Total Recall é uma biblioteca com mecanismo de busca; o Cortex é um secretário que
> lê a biblioteca, resume, e entrega na mesa só o que importa hoje.

---

## 1. Filosofia fundamental

| | Total Recall | Cortex / Anton |
|---|---|---|
| Postura | **Passiva** — "Não seleciono. Indexo tudo. E torno recuperável." | **Ativa** — decide o que importa agora e o que guardar para depois |
| Unidade | **Chunk** de transcript bruto (~1500 chars) | **Engram** destilado (regra, lição, fato de identidade) |
| O que sobrevive | Tudo — a conversa inteira vira corpus | Só o que foi *extraído* como aprendizado durável |
| Curadoria | **Nenhuma** (só heurísticas de peso) | **Central** — encoding gate, consolidação, dedup/vacuum |

O README do Total Recall se define **por oposição** ao auto-memory nativo do Claude,
que "seleciona o que *parece* relevante e descarta o resto". O Cortex *é* esse
seletor — só que muito mais sofisticado.

## 2. O que conta como "memória"

**Total Recall** — memória = histórico literal. Faz parse dos JSONL, pareia
`[Usuário]↔[Claude]`, guarda o texto. Blocos internos (`thinking`, `tool_result`)
entram só quando batem em marcadores de decisão, e mesmo assim como **trechos crus**.

**Cortex** — memória = conhecimento destilado, tipado em 4 classes (cada uma com
análogo cerebral):

| Tipo | Conteúdo | Arquivo | Análogo |
|---|---|---|---|
| **Identity** | fatos do usuário (nome, fuso, preferências) | `profile.md` | córtex pré-frontal medial |
| **Rules** | gates de comportamento (Always/Never/When) | `rules.md` | gânglios da base + OFC |
| **Lessons** | fatos semânticos destilados | `lessons.md` | lobo temporal anterior |
| **Topics** | expertise de domínio por slug | `topics/*.md` | áreas de associação cortical |

O `Engram` carrega `kind`, `scope` (global/project), `confidence`, `topic`, `source`
(user/consolidation/llm) e `id` = SHA-256 do texto. Memória **com proveniência e
confiança**, não só texto.

## 3. Armazenamento — a maior divergência técnica

| | Total Recall | Cortex |
|---|---|---|
| Backend | **SQLite WAL** | **Arquivos Markdown** (`~/.anton/memory/`) |
| Índices | `chunks_vec` (sqlite-vec 1024d) + `chunks_fts` (FTS5/BM25) | nenhum — texto plano com `<!-- key:value -->` |
| Embeddings | **qwen3-embedding:4b** via Ollama, instruction-aware | **nenhum** |
| Busca | vetorial + keyword | **só keyword + filtro de metadados** |

Inversão notável: o Total Recall é pesado em infraestrutura de recuperação porque
precisa achar agulha em palheiro de milhares de chunks. O Cortex dispensa tudo isso —
sua memória já é pequena e curada. Memória curada cabe no orçamento de tokens do
prompt direto.

## 4. Recuperação — "o que importa agora"

**Total Recall** recupera *sob demanda* (`/recall <query>`): pipeline de 5 estágios —
pré-processamento (abreviações PT, fuzzy) → classificação adaptativa de pesos
(semântico 70/30 × técnico 25/75) → busca paralela vetor+FTS5 → combinação com piso de
confiança (0.42) → **re-rank MMR** (λ=0.7). Mais **decaimento temporal** (meia-vida 30
dias), com decisões arquiteturais **isentas**.

**Cortex** recupera *automaticamente, todo turno*, via `build_memory_context()`: monta
seções no system prompt (`## Your Memory — Identity`, `## Your Memory — Global Rules`,
`## Your Memory — Project Rules`, `## Your Memory — Global/Project Lessons`). Quando as
regras estouram ~6000 chars, `_retrieve_relevant_rules()` usa **um LLM** para escolher
só as regras condicionais (When/If) relevantes à mensagem; Always/Never carregam
sempre. Detalhe: injeta as memórias **rotuladas como sendo do próprio agente**.

> **Total Recall = pull** (você puxa quando lembra de perguntar).
> **Cortex = push** (a memória chega ao agente todo turno, sem pedir).
> O Total Recall julga relevância com **matemática de similaridade**; o Cortex julga
> com **raciocínio de LLM** (cue-dependent retrieval).

## 5. Escrita de memória

**Total Recall não escreve memória.** Só *indexa* o que o Claude Code já gravou nos
JSONL. Não há `encode`, destilação, nem "o que vale guardar".

**Cortex tem ciclo de escrita completo:**
- `encode()` roteia engrams (profile → identidade, rules → `encode_rule()`,
  lessons → `encode_lesson()`).
- `encoding_gate()` controla confirmação por modo: *autopilot* grava tudo, *copilot*
  confirma baixa confiança, *off* desliga.
- **Consolidator (sleep replay)**: após sessão, `should_replay()` decide se vale
  revisar (≥5 cells, qualquer erro, marca "cancelled/killed"); `replay_and_extract()`
  comprime a sessão e pergunta ao LLM *"se fosse refazer, o que diria a si mesmo?"*,
  extraindo até 5 lições estruturadas. Aprendizado offline a partir da experiência —
  sobretudo dos erros.
- `vacuum()`/`compact_all()` deduplicam via LLM; `maybe_update_identity()` extrai
  identidade passivamente.

## 6. Aprendizado ao longo do tempo

| | Total Recall | Cortex |
|---|---|---|
| Melhora com uso? | Não, só cresce | **Sim** — consolida, reforça, dedup |
| Aprende com erros? | Não (só indexa o erro como texto) | **Sim** — Consolidator + Cerebellum |
| Esquece? | "Esquecimento" só por decaimento de score | Dedup/vacuum podam de fato |
| Feedback loop | Nenhum | encode → consolidate → reinforce → vacuum |

## 7. Componentes irmãos do Anton

- `cerebellum.py` — aprendizado supervisionado de erro a partir de falhas de células.
- `acc.py` (córtex cingulado anterior) — detecção de padrões em nível de turno.
- `skills.py` — memória procedural (skills).
- `reconsolidator.py` — migra formatos legados de memória para o schema novo.

---

## Veredito: complementares, não concorrentes

- **Total Recall** responde *"o que foi dito exatamente, lá atrás, sobre X?"* —
  recuperação de alta-fidelidade de tudo. Memória **episódica de longo prazo, completa
  e fria**.
- **Cortex** responde *"como devo me comportar agora, dado tudo que aprendi?"* —
  destilação de comportamento. Memória **semântica/procedural quente e curada**.

> Simetria elegante: Total Recall guarda **episódios crus e busca semanticamente**;
> Cortex guarda **semântica destilada e busca por raciocínio**. Cada um é forte
> exatamente onde o outro é fraco.

**O que o Total Recall poderia roubar do Cortex:** uma camada de **consolidação** que
periodicamente lê os chunks indexados e destila "lições" de alto nível (regras,
decisões, gotchas) numa segunda camada curada. Hoje o Total Recall já *detecta*
marcadores arquiteturais (e os isenta do decay), mas só os usa para **ponderar busca**,
nunca para **promover** aquilo a conhecimento de primeira classe.

**O que o Cortex poderia roubar do Total Recall:** **embeddings + sqlite-vec**, para
quando a memória curada crescer além do orçamento de prompt e o filtro de
keyword/metadados começar a perder recall.

---

## Fontes

- [`mindsdb/anton`](https://github.com/mindsdb/anton) — `anton/core/memory/`:
  `cortex.py`, `hippocampus.py`, `consolidator.py`, `base.py`, `acc.py`,
  `cerebellum.py`, `skills.py`, `reconsolidator.py`.
- [MindsHub — Anton](https://mindshub.ai/agents/anton).
- Total Recall: código em `src/total_recall/` deste repositório; `README.md`.
