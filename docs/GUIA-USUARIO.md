# Guia do Usuário — Total Recall

> Este guia cobre tudo que você precisa saber para usar o Total Recall no dia a dia: como a indexação funciona, o que é pesquisável, os limites do sistema, e como tirar o máximo da busca.

---

## Índice

1. [O que o Total Recall vê](#1-o-que-o-total-recall-vê)
2. [Como a indexação funciona](#2-como-a-indexação-funciona)
3. [Como a busca funciona](#3-como-a-busca-funciona)
4. [Erros de digitação e variações](#4-erros-de-digitação-e-variações)
5. [Comandos de referência](#5-comandos-de-referência)
6. [Usando dentro do Claude Code — skill /recall](#6-usando-dentro-do-claude-code--skill-recall)
7. [Rotina recomendada](#7-rotina-recomendada)
8. [Perguntas frequentes](#8-perguntas-frequentes)
9. [Limites do sistema — quando "nenhum resultado" é a resposta correta](#9-limites-do-sistema--quando-nenhum-resultado-é-a-resposta-correta)
10. [Busca cruzada com o total-recall-codex](#10-busca-cruzada-com-o-total-recall-codex)
11. [`--format table`: lendo a barra de cobertura e encadeando termos](#11-format-table-lendo-a-barra-de-cobertura-e-encadeando-termos)

---

## 1. O que o Total Recall vê

### Escopo: todos os projetos, não só o atual

O Total Recall indexa **todas as sessões em `~/.claude/projects/`**, independente de qual projeto estava ativo. Isso é intencional: você frequentemente vai querer buscar uma decisão que foi tomada numa sessão de outro projeto.

Na prática, quando você roda `total-recall index`, ele varre todos os subdiretórios de `~/.claude/projects/` e indexa cada arquivo `.jsonl` encontrado. Cada sessão recebe um `project_label` derivado do nome do diretório:

```
~/.claude/projects/
├── -Users-criacao-Library-...-AGENTES-CLAUDE/   → label: AGENTES/CLAUDE
├── -Users-criacao-Library-...-COMENTARIOS-TIKTOK/ → label: COMENTARIOS/TIKTOK
└── -Users-criacao/                               → label: criacao
```

Você pode filtrar por projeto na busca:

```bash
# Só sessões do projeto de agentes
total-recall search "arquitetura de memória" | grep AGENTES
```

Ou verificar de onde vêm os resultados:

```bash
total-recall sessions
```

### O que fica de fora por padrão

**Subagentes** (`subagents/*.jsonl`) são excluídos por padrão. São sessões curtas e ruidosas geradas automaticamente pelo Claude Code para tarefas específicas — geralmente mais ruído do que sinal. Para incluí-los:

```bash
total-recall index --subagents
```

**Sessões vazias** (0 mensagens) são indexadas mas produzem 0 chunks, então não aparecem em buscas.

### O que é extraído de cada sessão

O parser processa cada JSONL em duas passadas:

**Passada 1 — Exchanges** (conteúdo principal, peso total):
Cada par pergunta-resposta forma um chunk. Você pergunta algo, o Claude responde — isso vai junto, como uma unidade. É o que você vai encontrar na maior parte das buscas.

**Passada 2 — Blocos internos seletivos** (peso reduzido):
Partes do raciocínio interno do Claude (`thinking`) e saídas de ferramentas (`tool_result`) são indexadas **somente quando contêm linguagem de decisão ou diagnóstico**: "decidimos", "ADR", "o usuário quer", "root cause", "arquitetura", "o problema é", etc.

Isso significa que frases que o Claude disse internamente — mas não na resposta visível — são recuperáveis, desde que sejam sobre algo relevante.

---

## 2. Como a indexação funciona

### Indexação incremental (padrão)

```bash
total-recall index
```

Comportamento:
- Varre todos os `.jsonl` em `~/.claude/projects/`
- Compara o hash SHA-256 de cada arquivo com o que está no banco
- Processa apenas arquivos **novos** (nunca vistos) ou **alterados** (sessão que cresceu)
- Arquivos inalterados são ignorados completamente

Uma sessão "alterada" significa que você continuou conversando nela depois da última indexação. Nesse caso, o sistema deleta os chunks antigos daquela sessão e reindexava do zero — mais simples e correto do que tentar fazer diff de JSONL.

### Quando usar indexação incremental

- No início de uma nova sessão de trabalho
- Depois de uma sessão longa para capturar o que foi discutido
- Rotineiramente, se quiser manter o índice atualizado

Como é rápido (só processa o que mudou), pode rodar com frequência sem custo.

### Reindexação completa (full)

```bash
total-recall index --full
```

Comportamento:
- Apaga **tudo**: sessões, chunks, vetores, FTS5, cache de embeddings
- Recria a tabela vetorial com as dimensões configuradas
- Reindexada todas as sessões do zero

Quando usar:
- Depois de trocar o modelo de embedding (ex: nomic → qwen3)
- Depois de mudar a dimensão dos vetores
- Se o banco ficou corrompido ou inconsistente
- Se quiser começar do zero por qualquer razão

> ⚠️ O `--full` apaga o cache de embeddings. Com muitas sessões e Ollama disponível, pode demorar alguns minutos — cada chunk é embedado individualmente.

### Verificar o estado atual

```bash
total-recall status
```

Mostra:
- Quantas sessões e chunks estão indexados
- Quantos têm embedding vetorial
- Qual modelo e dimensão estão ativos
- Quando foi a última indexação

---

## 3. Como a busca funciona

### Dois motores, um resultado

Cada busca combina dois sinais em paralelo:

```
query: "como decidimos sobre sqlite-vec"
         │
         ├─ Motor vetorial (70%)
         │   Converte a query em vetor via qwen3-embedding:4b
         │   com instrução de retrieval. Encontra chunks semanticamente
         │   próximos, mesmo que não usem as mesmas palavras.
         │
         └─ Motor keyword / FTS5 (30%)
             Tokeniza a query e busca no índice de texto completo.
             Encontra matches exatos de palavras, siglas, nomes.
         │
         ▼
    Scores combinados → temporal decay → MMR → resultados
```

**O que o vetor faz bem**: paráfrases, sinônimos, consultas abstratas, cross-lingual (query em inglês, conteúdo em português).

**O que o FTS5 faz bem**: termos exatos, siglas (`ADR`, `WAL`, `FTS5`), identificadores de código, nomes de arquivos.

### Temporal decay

Resultados mais recentes pesam mais. O score é multiplicado por `2^(-dias/30)` — a cada 30 dias, o peso cai pela metade.

**Exceção**: chunks que contêm linguagem de decisão arquitetural não decaem. Uma decisão de dois meses atrás continua com peso total.

### MMR — sem redundância nos resultados

O re-ranking por Maximal Marginal Relevance garante que os 5 resultados não sejam variações do mesmo parágrafo. A cada item selecionado, o próximo candidato é penalizado pela similaridade com os já escolhidos. Resultado: diversidade real nos resultados.

---

## 4. Erros de digitação e variações

A partir da V02, o Total Recall tem três camadas de tolerância léxica que
corrigem automaticamente erros comuns de digitação. Você não precisa fazer
nada — a correção acontece na hora da busca.

### O que é corrigido automaticamente

**Separadores técnicos** — hífens e underscores são tratados como espaços:

```bash
total-recall search "total recall"    # encontra "total-recall"
total-recall search "session id"      # encontra "session_id"
total-recall search "sqlite vec"      # encontra "sqlite-vec"
```

**Abreviações PT-BR** — 38 abreviações informais são expandidas:

```bash
total-recall search "vc decidiu"      # encontra "você decidiu"
total-recall search "pq escolhemos"   # encontra "porque escolhemos"
total-recall search "tbm quero"       # encontra "também quero"
```

Lista parcial: `vc→você`, `pq→porque`, `tbm→também`, `hj→hoje`, `mt→muito`,
`nao→não`, `blz→beleza`, `vlw→valeu`, `repo→repositório`, `db→database`, `msg→mensagem`.

**Erros de digitação** (via rapidfuzz) — para palavras com 4+ caracteres,
o sistema busca variantes similares no vocabulário indexado:

```bash
total-recall search "sqilte"          # encontra "sqlite"
total-recall search "chromdb"         # encontra "chromadb"
total-recall search "embeding"        # encontra "embedding"
```

O threshold de similaridade é 85% — erros de 1-2 caracteres em palavras
com 5+ letras são corrigidos. Palavras curtas (≤ 3 chars) não passam pelo
fuzzy para evitar falsos positivos.

### O que NÃO é corrigido

- **Palavras completamente diferentes**: `busca` não encontra `pesquisa` via FTS5
  (o motor vetorial pode cobrir isso semanticamente)
- **Abreviações não cadastradas**: apenas as 38 da tabela interna são expandidas
- **UUIDs e session IDs**: nunca são expandidos por fuzzy

### Dica: queries descritivas continuam sendo mais robustas

Mesmo com a tolerância léxica, uma query descritiva sempre funciona melhor
que um termo isolado:

```bash
# Bom — encontra pelo contexto
total-recall search "renomear pasta agente de memória"

# Também funciona agora — corrige o typo
total-recall search "sqilte vec configuração"
```

### Queries em inglês encontram conteúdo em português (e vice-versa)

O qwen3-embedding:4b tem suporte cross-lingual genuíno. Isso funciona bem:

```bash
# Query em inglês, conteúdo estava em português
total-recall search "what did we decide about vector storage"
# → encontra "decidimos pelo sqlite-vec porque..."

# Query em português, conteúdo estava em inglês
total-recall search "como configurar o ambiente"
# → pode encontrar "set up the environment with..."
```

---

## 5. Comandos de referência

### `total-recall index`

```bash
total-recall index                  # Incremental (só novos/alterados)
total-recall index --full           # Reindexar tudo do zero
total-recall index --subagents      # Incluir sessões de subagentes
total-recall index --full --subagents
```

### `total-recall search`

```bash
total-recall search "query"                              # Busca padrão (5 resultados)
total-recall search "query" -n 10                        # Mais resultados
total-recall search "query" --session 9739fab2           # Filtrar por sessão (prefixo aceito)
total-recall search "query" --format context             # Para injeção no Claude
total-recall search "query" --format json                # Para processamento
total-recall search "query" --format rich                # Visual (padrão)
total-recall search "query" --format context --output -auto-        # Salva clipping automático
total-recall search "query" --format context --output meu-clip.md  # Salva com nome manual
total-recall search "query" --format pointers            # Ponteiros: 1 citação completa por sessão, resto resumido
total-recall search "query" --format table               # Tabela com barra de cobertura por termo (░▒█)
total-recall search "query" --source both                # Busca cruzada com o total-recall-codex (ver seção 10)
```

O formato `context` é o mais útil dentro do Claude Code — produz um bloco Markdown estruturado pronto para ser interpretado pelo modelo. `pointers` é melhor quando a busca traz muitas sessões diferentes e você quer varrer rápido antes de aprofundar numa só. **`table`** é o melhor pra decidir *qual* resultado vale a pena ler quando a query tem 2+ termos: cada segmento da barra mostra se aquele termo específico bateu literal (`█`), só via correção fuzzy (`▒`) ou não apareceu (`░`) — em vez do score decimal bruto, que não é comparável entre buscas diferentes (a fórmula muda com o modo de peso da query). Um resultado com todos os segmentos acesos é um match completo, mesmo que não seja o 1º colocado no ranking por score.

```
Termos: ①duckdb ②analista     █ literal · ▒ fuzzy/abrev · ░ ausente

#  Relevância          Fonte          Origem       Sessão                              Idade
─  ──────────────────  ─────────────  ───────────  ──────────────────────────────────  ─────
1  [█████|░░░░░] 100%  VECTOR + FTS5  CLAUDE-CODE  subagents · agent-a0                17d
    ┃ ...trecho com "duckdb" mas sem "analista"...
5  [█████|█████] 82%   FTS5           CODEX        vozes-da-comunidade-v04 · 019f7028  17d
    ┃ ...trecho com os dois termos juntos — o match completo de verdade...
```

Os clippings são salvos em `~/.total-recall/clips/` com cabeçalho de data/hora.

### `total-recall backfill-embeddings`

```bash
total-recall backfill-embeddings
```

Preenche o vetor de chunks que ficaram com `has_embedding=0` — normalmente porque o Ollama estava fora do ar durante uma indexação anterior (a indexação continua funcionando em modo FTS5-only nesse caso, mas o chunk perde a busca semântica até isso ser corrigido). Verifique se há chunks pendentes com `total-recall doctor` (linha "Chunks sem embedding").

Diferença importante em relação a `total-recall index --full`: **não apaga nada**. Só completa o que faltou, em transações curtas — pode rodar com outro terminal usando `/recall` ao mesmo tempo sem derrubar a busca local (a busca vetorial só fica temporariamente mais fraca — modo FTS5-only nos chunks ainda pendentes — enquanto o backfill compete pelo Ollama). Prefira este comando a `--full` sempre que o problema for só embedding faltando, não corrupção de dados.

### `total-recall sessions`

```bash
total-recall sessions               # Lista todas as sessões
total-recall sessions --project AGENTES  # Filtra por projeto (substring)
```

### `total-recall export`

```bash
total-recall export 31c6d284        # Exporta sessão para Markdown
                                    # Salvo em ~/.total-recall/exports/
```

Útil quando você quer ler a sessão completa, não apenas trechos.

### `total-recall status`

```bash
total-recall status
```

Saída típica:
```
Total Recall — Status

  Banco: ~/.total-recall/total-recall.db (8.13 MB)
  Sessões indexadas: 6
  Chunks: 596 (596 com embedding)
  Cache de embeddings: 545 entradas
  Última indexação: 2026-03-24 22:02 (6 arquivos, 596 chunks)
  Embedding: ollama / qwen3-embedding:4b (1024 dims)
  Sessões JSONL disponíveis: 46
```

"Sessões JSONL disponíveis" mostra o total de arquivos no disco. Se for muito maior que "Sessões indexadas", rode `total-recall index` para atualizar.

### `total-recall init`

```bash
total-recall init
```

Só precisa rodar uma vez (ou depois de reinstalar). Cria o banco de dados, os diretórios, e instala a skill `/recall` em `~/.claude/skills/recall/SKILL.md`.

---

## 6. Usando dentro do Claude Code — skill /recall

Este é o uso mais poderoso do sistema. Em vez de sair para o terminal, você acessa a memória de dentro da conversa.

### Tabela comparativa: `/recall` vs `total-recall search`

| | `/recall` (skill, dentro do Claude) | `total-recall search` (CLI, terminal) |
|---|---|---|
| **Onde roda** | Dentro da sessão ativa do Claude Code | Terminal, fora do Claude |
| **Quem interpreta** | Claude analisa e sintetiza os resultados | Você lê os resultados diretamente |
| **Saída padrão** | Markdown renderizado com análise | Terminal colorido (rich) ou texto |
| **Highlighting** | **`negrito+código`** nos termos | ANSI amarelo no terminal |
| **Filtro por sessão** | `/recall query --session abc123` | `--session abc123` |
| **Mais resultados** | `/recall query --limit 12` | `-n 12` |
| **Salvar clipping** | `/recall query --clip` | `--output -auto-` |
| **Aprofundar sessão** | `/recall query --session abc123 --limit 15` | `--session abc123 -n 15` |
| **Exportar sessão** | não disponível | `total-recall export <session-id>` |
| **Formato JSON** | não disponível | `--format json` |
| **Busca cruzada (codex)** | frase `cruzada`/`buscar-no-codex` no texto | `--source both` / `--source codex` |

### Flags disponíveis no /recall

```
/recall <query>                          # busca padrão (8 resultados)
/recall <query> --clip                   # salva resultados como clipping Markdown
/recall <query> --limit 12               # mais resultados
/recall <query> --session abc123         # filtra por sessão (prefixo aceito)
/recall <query> --session abc123 --clip  # filtrado + salvo
```

**Exemplos reais:**

```
/recall lancedb lancedb                            # variações do mesmo termo
/recall banco vetorial decisão --clip              # pesquisa + salva clipping
/recall Milvus --session c3b0e47e --limit 15       # aprofunda numa sessão específica
/recall o que decidimos sobre a arquitetura?       # query descritiva funciona bem
/recall sqlite WAL backup --clip                   # referência técnica salva para depois
/recall cruzada: decisão sobre o parser do codex   # também busca no total-recall-codex
/recall buscar-no-codex: erro de timeout no eval   # só no total-recall-codex
```

Os clippings ficam em `~/.total-recall/clips/` com nome gerado automaticamente (`2026-03-25_banco-vetorial-decisao.md`).

### O que acontece quando você usa /recall

A skill detecta as flags e frases-gatilho, executa `total-recall search "<query limpa>" --format context [--output -auto-] [--source both|codex]` e injeta os resultados no contexto da conversa. O Claude recebe os trechos estruturados com sessão, data, rótulo de origem (`[CLAUDE-CODE]`/`[CODEX]`, ver seção 10) e conteúdo, e responde com base neles.

### Quando usar /recall

- Quando mencionar algo de uma sessão passada ("lembra quando discutimos...") — use `/recall` antes de continuar
- Ao iniciar trabalho em um projeto com histórico — `/recall contexto do projeto X`
- Quando quiser citar a decisão correta, não a que você lembra — `/recall por que não usamos pgvector`
- Para recuperar código ou configuração que foi discutida — `/recall como configuramos o WAL no SQLite`
- Para criar uma referência consultável depois — `/recall tema importante --clip`

### Limitação importante

A skill só encontra o que já está indexado. Se você teve uma conversa hoje e não rodou `total-recall index` desde então, ela não aparece nos resultados do `/recall`. A rotina recomendada abaixo resolve isso.

---

## 7. Rotina recomendada

### Indexação automática via hooks (recomendado)

Em vez de rodar `total-recall index` manualmente, configure dois hooks no Claude Code que disparam automaticamente:

```json
// ~/.claude/settings.json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [{ "type": "command", "command": "total-recall index" }]
      }
    ],
    "PreCompact": [
      {
        "matcher": "",
        "hooks": [{ "type": "command", "command": "total-recall index" }]
      }
    ]
  }
}
```

**`SessionStart`** garante que ao abrir qualquer sessão do Claude Code, tudo de sessões anteriores já está indexado e pesquisável.

**`PreCompact`** indexa o conteúdo da sessão atual antes que o Claude compacte o contexto por limite de tokens. Sem esse hook, conteúdo recente de sessões longas só ficaria disponível no `/recall` após encerrar a sessão.

Se o Ollama não estiver ativo quando o hook disparar, o total-recall indexa via FTS5 (busca por keywords continua funcionando) e adiciona os embeddings vetoriais na próxima vez que o Ollama estiver disponível.

### Indexação manual (quando necessário)

```bash
total-recall index        # incremental — só sessões novas ou que cresceram
total-recall index --full # reindexação completa — obrigatório ao trocar de modelo
```

### Durante a sessão

Use `/recall` livremente no Claude Code. Não precisa sair para o terminal.

### Ao trocar de máquina

O banco fica em `~/.total-recall/total-recall.db`, local e não sincronizado. No novo ambiente, rode `total-recall index` para construir o índice local com as sessões disponíveis.

---

## 8. Perguntas frequentes

**O Total Recall vê esta sessão atual?**

Não em tempo real. O JSONL da sessão atual ainda está sendo escrito. Você precisa rodar `total-recall index` *depois* que a sessão terminar (ou enquanto está ativa, mas só captura o que foi escrito até aquele momento).

**Quanto espaço ocupa?**

O banco atual com 596 chunks e embeddings de 1024 dimensões ocupa 8 MB. A estimativa de crescimento é ~13 KB por chunk (texto + vetor + FTS5). Para 5.000 chunks, espere ~65 MB — confortável.

**O que acontece se o Ollama estiver offline?**

O sistema entra em modo FTS5-only automaticamente. A busca vetorial não funciona, mas a busca por palavras-chave continua operando normalmente. Quando o Ollama voltar, uma nova indexação completa (`--full`) embeda todos os chunks que ficaram sem vetor.

**Posso buscar em só uma sessão específica?**

Sim. Use `--session` com os primeiros caracteres do UUID:

```bash
total-recall search "qualquer coisa" --session 9739fab2
```

Funciona com prefixo — você não precisa do UUID completo.

**Como sei qual é o UUID de uma sessão?**

```bash
total-recall sessions
```

A primeira coluna é o UUID (exibido com 8 caracteres). Você pode usar esses 8 caracteres diretamente no `--session`.

**O que é "project_label" nos resultados?**

Um label legível derivado do nome do diretório de projeto no `~/.claude/projects/`. O diretório `-Users-criacao-Library-...-AGENTES-CLAUDE` vira `AGENTES/CLAUDE`. Não é configurável manualmente — é inferido automaticamente.

**Posso indexar sessões de outro computador?**

Não diretamente, mas você pode apontar o `TOTAL_RECALL_SESSIONS` para outro diretório:

```bash
TOTAL_RECALL_SESSIONS=/caminho/para/backup/.claude/projects total-recall index
```

---

---

## 9. Limites do sistema — quando "nenhum resultado" é a resposta correta

Esta seção explica o comportamento do sistema quando você busca por algo que **não está nas sessões indexadas** — e por que retornar zero resultados é mais honesto do que retornar resultados inventados.

### O problema: a busca vetorial sempre encontra algo

O motor vetorial converte sua query em um ponto num espaço de 1024 dimensões e busca os N pontos mais próximos no banco. O problema: ele **sempre responde**, independente de quão longe os vizinhos estejam. É como pedir ao GPS o restaurante mais próximo estando no meio do deserto — ele te dá uma resposta, mas não é útil.

Quando você busca um termo que nunca apareceu nas suas sessões, o sistema não encontra nada via FTS5 (busca por palavras-chave), e o motor vetorial devolve os "menos distantes" do espaço — que podem ser completamente irrelevantes. O resultado parece real: tem score, tem sessão, tem conteúdo. Mas é ruído.

**Exemplo real:** busca por `"netnografia"` (metodologia de pesquisa online) num banco que só contém conversas sobre Claude Code:

```
[1] ▓▓▓▓░░░░░░ 0.41 | AGENTES/CLAUDE — Sessão 4b8c4f15  ← ruído
    "O transcript daquela sessão está linkado no próprio sistema..."

[2] ▓▓▓░░░░░░░ 0.39 | AGENTES/CLAUDE — Sessão 4b8c4f15  ← ruído
    "Agora vou testar:"
```

Nenhum desses resultados tem qualquer relação com netnografia. O sistema estava devolvendo os chunks que habitam a região do espaço vetorial "menos longe" de "netnografia" — conceitos de rede/internet e documentação acadêmica, que vagamente se sobrepõem com sessões remotas e transcripts de conversas.

### Por que o espaço vetorial cria essa ilusão

Para visualizar, imagine uma versão 2D simplificada do espaço de 1024 dimensões:

```
                    ↑
                    │  [chunk: "sessão remota"]       × ← netnografia
                    │                       ·
                    │      [chunk: "GitHub link"]
                    │  [chunk: "transcript"]
                    │
   Claude Code ─────┼──────────────────────────────────→
   conversas        │
                    │
                    │
                         ← etnografia/pesquisa (espaço vazio)
```

O banco só contém pontos na região "Claude Code". "Netnografia" aterrissa num ponto vazio, na fronteira de conceitos de rede/pesquisa. O motor vetorial não sabe que aquela região é vazia — ele simplesmente retorna os 5 pontos menos distantes disponíveis.

A matemática explica o score baixo:

```
score = VECTOR_WEIGHT × (1 / (1 + distância_cosseno))
      = 0.7 × (1 / (1 + d))

Para score 0.41:
  d = 0.706  →  similaridade de cosseno = 0.294

Escala de referência:
  1.00 → mesmo texto
  0.85 → paráfrase próxima
  0.65 → mesmo tópico
  0.50 → tópicos relacionados
  0.29 → sem relação prática  ← netnografia
  0.00 → vetores ortogonais (aleatório)
```

Score 0.29 de similaridade de cosseno significa que o vetor de "netnografia" e o vetor do chunk retornado apontam quase em direções opostas no espaço — não há relação real.

### A solução: piso de confiança para resultados vector-only

O sistema aplica um filtro seletivo: **resultados recuperados exclusivamente pelo motor vetorial** (sem nenhum match por FTS5) são descartados se o score estiver abaixo de 0.42.

Resultados com contribuição FTS5 passam incondicionalmente — se o FTS5 encontrou o termo, ele literalmente existe no corpus. O filtro atua apenas no ruído vetorial puro.

```
Por que apenas vector-only?

Score máximo possível de um resultado puro FTS5:
  TEXT_WEIGHT × 1.0 = 0.3 × 1.0 = 0.30

Um threshold de 0.42 acima de 0.30 filtraria TODOS os resultados FTS5.
Por isso o filtro é aplicado seletivamente: só a resultados sem FTS5.
```

Com o piso configurado:

```
Busca por "netnografia" (não está no corpus):
  FTS5: 0 resultados
  Vetorial: 5 resultados, todos com score < 0.42
  → Todos filtrados → "Nenhum resultado encontrado" ✓

Busca por "arquitetura de memória" (está no corpus):
  FTS5: encontra matches literais → passa incondicionalmente
  Vetorial: scores 0.47–0.53 → acima do piso → passa ✓
  → Resultados genuínos retornados ✓
```

Você pode ajustar o piso via variável de ambiente se necessário:

```bash
TOTAL_RECALL_MIN_SCORE=0.50 total-recall search "query"  # mais restrito
TOTAL_RECALL_MIN_SCORE=0.35 total-recall search "query"  # mais permissivo
```

### `/recall` vs terminal: a diferença de comportamento

Antes do piso de confiança existir, havia uma diferença importante entre os dois modos de uso:

| | `/recall` (dentro do Claude) | `total-recall search` (terminal) |
|---|---|---|
| **Quem interpreta** | Claude lê e filtra os resultados | Você lê diretamente |
| **Comportamento com ruído** | Claude detecta que os resultados não têm relação com a query e responde "não encontrado" | Exibe os resultados — parece real, mas é ruído |
| **Honestidade** | Alta — Claude age como filtro inteligente | Dependia do usuário perceber os scores baixos |

---

## 10. Busca cruzada com o total-recall-codex

### O que é

Se você também usa Codex indexado pelo projeto irmão [`total-recall-codex`](https://github.com/jailsonsouto/total-recall-codex) na mesma máquina, dá pra consultar as duas coleções sem trocar de ferramenta. A leitura é sempre sob demanda e read-only — o Total Recall nunca escreve no banco do total-recall-codex, só abre e lê quando você pede.

### Quando usar cada modo

| Situação | Comando |
|---|---|
| Dia a dia — a resposta provavelmente está numa sessão sua do Claude Code | nada, o padrão já busca só aqui (mais rápido) |
| "Discuti isso, mas não lembro se foi aqui ou no Codex" | `--source both` / `/recall cruzada: ...` |
| Sabe que a decisão foi tomada trabalhando com Codex | `--source codex` / `/recall buscar-no-codex: ...` |

### Exemplos

```bash
# Dia a dia: rápido, só este banco (padrão, sem flag)
total-recall search "por que escolhemos sqlite-vec"

# "Cadê aquilo que discutimos, não lembro se foi aqui ou no Codex"
total-recall search "decisão do parser de turnos abortados" --source both

# Sei que rodei isso no Codex, quero só de lá
total-recall search "timeout no eval controlado" --source codex --format context
```

Dentro do Claude Code:

```
/recall cruzada: decisão sobre o parser de turnos abortados
/recall buscar-no-codex: timeout no eval controlado
```

### Como reconhecer a origem

Cada resultado vem com um rótulo entre colchetes — sempre, mesmo quando é o banco local, pra não obrigar você a adivinhar por ausência de marca:

```
[1] ▓▓▓▓▓▓░░░░ 0.82 | [CLAUDE-CODE] meu-projeto — Sessão abc12345
[2] ▓▓▓▓▓░░░░░ 0.71 | [CODEX] outro-projeto — Codex — Sessão def67890
```

### Aprofundando um resultado do Codex

Se o rótulo é `[CODEX]`, `--session <id>` sozinho não encontra nada — o padrão busca só o banco local. Inclua a origem:

```bash
total-recall search "..." --session def67890 --source codex --format context
```

### Isolamento

A leitura do banco do total-recall-codex é sempre read-only — conexão SQLite `mode=ro`, bloqueada a nível de driver, não só por convenção de código; escrever nela levanta erro tanto no sqlite quanto no Python. Os dois bancos nunca se tocam em disco: a fusão de `--source both` acontece só em memória, na hora de montar a resposta. Se o total-recall-codex não estiver instalado/indexado nessa máquina, `--source both` avisa em stderr e segue só com o banco local; `--source codex` sozinho, sem o banco irmão, retorna um erro claro em vez de silêncio.

O `/recall` já funcionava corretamente mesmo sem o piso — o Claude, ao receber os chunks, percebia que nenhum mencionava o termo buscado e informava o usuário. O filtro de score mínimo corrige o comportamento do CLI para que seja igualmente honesto, sem depender de interpretação humana.

### O que o sistema não pode recuperar

O piso de confiança é a mitigação certa para "termo ausente do corpus". Mas há outros limites que nenhuma configuração resolve:

- **Conceitos nunca discutidos**: se você nunca mencionou "netnografia" em nenhuma sessão, não há nada a recuperar. O sistema é memória — não inventa.
- **Sessões não indexadas**: conteúdo de sessões que não passaram pelo `total-recall index` é invisível.
- **Paráfrases sem sobreposição vetorial**: em casos raros, uma ideia pode ter sido expressa de forma tão diferente da query que nem o vetor consegue conectar. Nesses casos, tente reformular a query com outros termos.

---

## 11. `--format table`: lendo a barra de cobertura e encadeando termos

### O problema que esse formato resolve

O score combinado (vetor + FTS5, pesos que mudam com o tipo de query) não é comparável entre buscas diferentes — `0.24` numa busca não significa a mesma coisa que `0.24` noutra. `--format table` troca o score decimal bruto por um selo verificável, termo a termo:

```bash
total-recall search "sua query" --format table
```

```
Termos: ①termo1 ②termo2     █ literal · ▒ fuzzy/abrev · ░ ausente

#  Relevância          Fonte          Origem       Sessão                    Idade
─  ──────────────────  ─────────────  ───────────  ─────────────────────    ─────
1  [█████|░░░░░] 100%  VECTOR + FTS5  CLAUDE-CODE  projeto · abc12345       17d
    ┃ trecho destacado do resultado...
```

- **`█`** — o termo bateu literal (exato, ignorando maiúscula/acento)
- **`▒`** — só bateu via correção fuzzy (typo) ou palavra composta separada (ex.: `deltalake` → `delta lake`)
- **`░`** — o termo não apareceu de jeito nenhum nesse resultado
- **`%`** — relativo ao melhor resultado *dessa busca* (topo = 100%); não compare o `%` entre buscas diferentes, só dentro da mesma lista

### Encadeando 2, 3 ou 4 termos relacionados

O motor de busca trata múltiplos termos como alternativas (é "ou", não "e" estrito) — cada termo contribui pro ranking independente dos outros. Isso significa que **a barra de cobertura é a única forma prática de saber quais resultados batem em vários termos ao mesmo tempo**, já que a busca não filtra por "só quero os que têm todos".

```bash
# 2 termos
total-recall search "duckdb analista" --format table

# 3 termos
total-recall search "sqlite vec ollama" --format table

# 4 termos
total-recall search "sqlite vec fts5 ollama" --format table
```

Com 4 termos específicos (nenhum genérico), a cobertura mostra o quadro completo numa olhada:

```
Termos: ①sqlite ②vec ③fts5 ④ollama     █ literal · ▒ fuzzy/abrev · ░ ausente

#  Relevância          Fonte          Origem       Sessão                              Idade
─  ──────────────────  ─────────────  ───────────  ──────────────────────────────────  ─────
1  [██|██|██|██] 100%  VECTOR + FTS5  CODEX        vozes-da-comunidade-v04 · 019fc2a6  1d
3  [██|██|██|░░] 100%  VECTOR + FTS5  CLAUDE-CODE  AGENTES/CLAUDE · 31c6d284           4m
```

`[1]` tem os 4 termos; `[3]` tem 3 de 4 (falta "ollama") — mesmo score de 100%, cobertura bem diferente. Sem a barra, os dois pareceriam igualmente bons.

### Exemplo: o resultado certo nem sempre é o 1º colocado

Esse é o caso que motivou o formato inteiro. Buscando "duckdb analista", os 4 primeiros resultados por score só têm "duckdb" — o 5º, com score menor, é o único que tem os dois termos juntos:

```
Termos: ①duckdb ②analista     █ literal · ▒ fuzzy/abrev · ░ ausente

#  Relevância          Fonte          Origem       Sessão                              Idade
─  ──────────────────  ─────────────  ───────────  ──────────────────────────────────  ─────
1  [█████|░░░░░] 100%  VECTOR + FTS5  CLAUDE-CODE  subagents · agent-a0                17d
2  [█████|░░░░░] 100%  VECTOR + FTS5  CLAUDE-CODE  comunidade/v04 · 3c43004b           17d
5  [█████|█████] 82%   FTS5           CODEX        vozes-da-comunidade-v04 · 019f7028  17d
```

Sem a barra, `[5]` pareceria o pior resultado (menor score). Com ela, fica óbvio que é o único match completo.

### Exemplo: dois termos, cobertura total

Quando os termos aparecem sempre juntos no corpus (aconteceu bastante em conversas sobre "a Garimpeira" e "o chat"), a barra fica toda acesa — é o caso "chato" de confirmar, mas útil pra saber que não tem nada escondido:

```bash
total-recall search "chat garimpeira" --format table
```
```
Termos: ①chat ②garimpeira     █ literal · ▒ fuzzy/abrev · ░ ausente

1  [█████|█████] 100%  VECTOR + FTS5  CODEX        vozes-da-comunidade-v04 · 019f7028  17d
2  [█████|█████]  99%  VECTOR + FTS5  CODEX        vozes-da-comunidade-v04 · 019fc27d   1d
```

### Exemplo: o nível `▒` (fuzzy) em ação

Buscando um nome de produto colado sem espaço (`ducklake`), o sistema tenta a correção automática — e o trecho mostra de onde veio:

```bash
total-recall search "ducklake" --format table
```
```
Termos: ①ducklake     █ literal · ▒ fuzzy/abrev · ░ ausente

1  [██████████] 100%  VECTOR + FTS5  CODEX  vozes-da-comunidade-v04 · 019f7028  17d
    ┃ ## Concorrência e DuckLake — O formato nativo do DuckDB funciona melhor...
```

Nesse corpus específico "DuckLake" é escrito como uma palavra só (como GitHub, YouTube) — por isso bateu `█` (literal) mesmo sem você saber disso de antemão. Se o termo real do corpus tivesse espaço (como "Delta Lake"), o sistema tenta automaticamente a versão separada e mostra `▒` pra indicar que foi uma correção, não um match exato.

### Armadilha a evitar: misturar termo raro com termo genérico demais

```bash
total-recall search "deltalake próximo" --format table
```
```
Termos: ①deltalake ②próximo     █ literal · ▒ fuzzy/abrev · ░ ausente

1  [▒▒▒▒▒|█████] 100%  FTS5   CODEX        briefings · 019d917a       3m
3  [░░░░░|█████]  99%  FTS5   CODEX        vozes-da-comunidade · 019d310c  4m
```

"Próximo" é uma palavra tão comum que domina o ranking sozinha — nenhum desses 5 resultados é realmente sobre Delta Lake (o `▒` do `[1]` bateu por coincidência, na palavra "detalha", não no produto). Buscar `deltalake` sozinho, sem "próximo", encontra o conteúdo real. **Lição prática**: encadeie termos que sejam todos específicos entre si; evite combinar um termo raro com uma palavra do dia a dia (próximo, sistema, modelo, dados).

---

*Para detalhes de arquitetura e decisões de design, veja o [README](../README.md) e os documentos em `docs/`.*
