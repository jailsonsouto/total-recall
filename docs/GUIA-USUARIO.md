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
```

O formato `context` é o mais útil dentro do Claude Code — produz um bloco Markdown estruturado pronto para ser interpretado pelo modelo.

Os clippings são salvos em `~/.total-recall/clips/` com cabeçalho de data/hora.

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
```

Os clippings ficam em `~/.total-recall/clips/` com nome gerado automaticamente (`2026-03-25_banco-vetorial-decisao.md`).

### O que acontece quando você usa /recall

A skill detecta as flags, executa `total-recall search "<query limpa>" --format context [--output -auto-]` e injeta os resultados no contexto da conversa. O Claude recebe os trechos estruturados com sessão, data e conteúdo, e responde com base neles.

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

### No início de cada sessão de trabalho

```bash
total-recall index
```

Captura tudo que foi discutido desde a última vez. Rápido (incremental).

### Durante a sessão

Use `/recall` livremente no Claude Code. Não precisa sair para o terminal.

### Ao trocar de máquina

O banco fica em `~/.total-recall/total-recall.db` — local, não sincronizado. No Windows, rode `total-recall index` para construir o índice local com as sessões disponíveis naquele ambiente.

### Ao mudar o modelo de embedding

```bash
total-recall index --full
```

Obrigatório. O banco precisa ser recriado com os novos vetores.

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

*Para detalhes de arquitetura e decisões de design, veja o [README](../README.md) e os documentos em `docs/`.*
