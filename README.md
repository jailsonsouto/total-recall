# Total Recall

> *Memória de longo prazo pesquisável para sessões do Claude Code CLI*

---

## Motivação

O Claude Code persiste cada sessão como um arquivo JSONL em `~/.claude/projects/`. Esse arquivo contém tudo: perguntas, respostas, raciocínio interno (`thinking`), resultados de ferramentas, decisões arquiteturais. Quando a sessão termina — por compressão de contexto, queda de energia ou simples fechamento — todo esse conhecimento torna-se opaco. Existe no disco, mas não é recuperável.

O mecanismo nativo de `auto-memory` do Claude Code mitiga parcialmente esse problema, mas opera por seleção discreta: extrai o que o modelo julga relevante no momento, descartando o restante. Decisões técnicas formuladas de forma implícita, raciocínios exploratórios que levaram a uma conclusão correta, diagnósticos de bugs — tudo isso tende a ser descartado por não satisfazer os critérios de relevância instantânea do auto-memory.

**Total Recall** resolve o problema na origem: em vez de selecionar o que preservar, indexa *tudo*, e oferece recuperação semântica sobre o corpus completo.

---

## O que é

Um sistema local de indexação e recuperação de informação construído sobre o corpus bruto de sessões do Claude Code. Opera inteiramente no dispositivo — sem dependências de API externas, sem transmissão de dados.

O pipeline principal é:

```
~/.claude/projects/**/*.jsonl
         │
         ▼ total-recall index
         │
         ├─ Parsing JSONL → exchanges + blocos seletivos
         ├─ Chunking com overlap (exchange-based)
         ├─ Embedding com qwen3-embedding:4b (1024 dims)
         └─ Armazenamento em SQLite WAL
                ├─ chunks_vec  (sqlite-vec, busca vetorial)
                └─ chunks_fts  (FTS5/BM25, busca por keywords)
         │
         ▼ total-recall search "query"
         │
         ├─ Busca híbrida (70% vetorial + 30% keyword)
         ├─ Temporal decay (meia-vida 30 dias; decisões não decaem)
         └─ MMR re-ranking (diversidade nos resultados)
```

A busca é acessível via CLI diretamente no terminal, ou via skill `/recall` de dentro de qualquer sessão ativa do Claude Code.

---

## Decisões de Arquitetura

### 1. Exchange-based chunking

A unidade semântica fundamental não é a mensagem individual, mas o *exchange* — o par (pergunta do usuário, resposta do assistente). Fragmentar por mensagem produz chunks semanticamente incompletos: a resposta, isolada da pergunta que a motivou, perde boa parte do seu significado recuperável.

Respostas longas são subdivididas com overlap de 200 caracteres para preservar continuidade entre chunks adjacentes.

### 2. Indexação seletiva de blocos internos

Os JSONLs do Claude Code contêm, além das mensagens visíveis, blocos `thinking` (raciocínio interno do modelo) e `tool_result` (saída de ferramentas). Esses blocos têm valor informacional assimétrico: a maior parte é ruído operacional (tentativas descartadas, logs verbosos), mas uma fração contém decisões arquiteturais, diagnósticos de causa-raiz e intenções do usuário que não aparecem em nenhum outro lugar.

A solução adotada é indexação *condicional*: blocos internos são incluídos apenas quando contêm marcadores lexicais de conteúdo valioso — `"decidimos"`, `"ADR"`, `"root cause"`, `"o usuário quer"`, `"trade-off"`, entre outros. Chunks assim classificados recebem pesos de relevância reduzidos (`thinking`: 0.6, `tool_context`: 0.7) para não competirem em pé de igualdade com conteúdo explícito.

### 3. Busca híbrida

O sistema combina dois sinais complementares:

- **Busca vetorial** (peso 0.7): recuperação semântica via similaridade de cosseno sobre embeddings de 1024 dimensões. Cobre paráfrases, consultas ambíguas e recuperação *cross-lingual* (consultas em inglês sobre conteúdo em português, e vice-versa).
- **Busca por palavras-chave** via FTS5/BM25 (peso 0.3): cobre termos exatos, siglas, identificadores de código e nomes próprios que embeddings tendem a tratar com imprecisão.

Num sistema puramente vetorial, o embedding carrega toda a carga de recuperação. Num sistema híbrido, cada componente faz o que faz melhor. Isso permite usar um modelo de embedding de 1024 dimensões com qualidade equivalente a sistemas que exigem 2560+ dimensões em modo vetorial puro.

### 4. Temporal decay com exceção para decisões

Sessões recentes são naturalmente mais relevantes para o contexto corrente. Um decay exponencial com meia-vida de 30 dias pondera scores pela idade do chunk: `score × 2^(-dias/30)`.

A exceção é deliberada: chunks que contêm linguagem de decisão arquitetural (`"decidimos"`, `"vs"`, `"ao invés de"`, `"arquitetura"`, `"schema"`) são tratados como *atemporais* e não sofrem decay. Uma decisão tomada há seis meses permanece tão relevante quanto no dia em que foi tomada.

### 5. MMR re-ranking

Maximal Marginal Relevance seleciona iterativamente os resultados que maximizam a combinação de relevância individual e distância dos itens já selecionados (similaridade de Jaccard sobre tokens). Com λ=0.7, o critério favorece relevância mas penaliza redundância — evitando que os cinco primeiros resultados sejam variações do mesmo parágrafo da mesma sessão.

### 6. Delta indexing

Cada arquivo JSONL indexado tem seu hash SHA-256 armazenado. Execuções subsequentes de `total-recall index` processam apenas arquivos novos ou modificados. Arquivos modificados (sessões que cresceram) são deletados e reindexados integralmente — mais simples e correto do que diff parcial.

### 7. Graceful degradation

Se o Ollama não estiver disponível, o sistema opera em modo FTS5-only: chunks são armazenados sem vetor, mas permanecem plenamente indexados e recuperáveis via busca por palavras-chave. O modo híbrido é restaurado automaticamente na próxima execução com Ollama ativo.

---

## Stack

| Componente | Papel |
|---|---|
| **SQLite WAL** | Banco único, crash-safe, sem servidor |
| **sqlite-vec** | Tabela virtual para busca vetorial por similaridade (cosine) |
| **FTS5** | Índice de texto completo com ranking BM25 |
| **qwen3-embedding:4b** | Modelo de embedding multilíngue (1024 dims, instruction-aware) |
| **Ollama** | Runtime local para o modelo de embedding |
| **Click** | Interface de linha de comando |

### Por que qwen3-embedding:4b

O corpus é bilíngue (pt-BR e inglês), técnico, e consultado por queries abertas do tipo "como decidimos sobre X?" ou "qual foi o diagnóstico do bug Y?". Nesse perfil, três propriedades do modelo são determinantes:

1. **Suporte multilíngue nativo** — o Qwen3-Embedding foi treinado com suporte a 100+ idiomas, com desempenho forte em recuperação *cross-lingual*.
2. **Instruction-aware** — o modelo suporta instruções explícitas para queries de retrieval, separadas dos documentos. Queries recebem o prefixo `Instruct: ... \nQuery: {text}`; documentos são embedados sem instrução. Essa assimetria melhora o alinhamento semântico entre consulta e documento.
3. **Benchmark MTEB multilingual** — score 69.45 para a variante 4B, contra ~60 do `nomic-embed-text`, que foi o modelo adotado na fase inicial do projeto.

#### Nota sobre a escolha original: nomic-embed-text

O projeto começou com `nomic-embed-text` (768 dimensões) — uma decisão deliberada e bem fundamentada para o momento: modelo maduro, amplamente validado pela comunidade, integração direta com Ollama, e default de referência adotado por sistemas como o OpenClaw. Para um MVP cuja prioridade era verificar o pipeline de indexação e recuperação, essa era a escolha correta.

A migração para o Qwen3-Embedding foi motivada por uma necessidade concreta que se manifestou em produção: a natureza bilíngue do corpus (conversas em pt-BR com terminologia técnica em inglês) e o padrão de queries semânticas abertas demandavam um modelo com capacidade *cross-lingual* genuína. O `nomic-embed-text` opera bem em inglês monolíngue; para o perfil específico deste projeto, o Qwen3 oferece ganho mensurável. A decisão de manter 1024 dimensões em vez de 2560 — dimensão nativa máxima do modelo — foi igualmente deliberada: em sistema híbrido com FTS5, o vetor não precisa carregar sozinho toda a carga semântica, e 1024 dimensões oferece o equilíbrio correto entre qualidade e custo computacional neste hardware.

---

## Instalação

**Pré-requisitos**: Python 3.9+, Ollama instalado e rodando.

```bash
# Clonar ou navegar até o projeto
cd projetos/total-recall

# Criar ambiente virtual com Python 3.12+
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .

# Baixar o modelo de embedding
ollama pull qwen3-embedding:4b

# Inicializar banco de dados e instalar skill /recall
total-recall init

# Indexar todas as sessões
total-recall index
```

Para acesso global (sem ativar o venv manualmente), copiar o wrapper para o PATH:

```bash
cp .local-bin/total-recall ~/.local/bin/total-recall
chmod +x ~/.local/bin/total-recall
```

---

## Uso

### CLI

```bash
# Busca semântica + keyword
total-recall search "como decidimos sobre pgvector"

# Mais resultados
total-recall search "arquitetura memoria viva" --format context -n 10

# Filtrar por sessão específica (prefixo do UUID)
total-recall search "renomear pasta" --session 9739fab2

# Salvar resultados como clipping Markdown
total-recall search "lancedb decisão" --format context --output -auto-
# → ~/.total-recall/clips/2026-03-25_lancedb-decisao.md

# Exportar sessão completa para Markdown
total-recall export 31c6d284
# → ~/.total-recall/exports/31c6d284.md

# Listar sessões indexadas
total-recall sessions

# Estado do sistema
total-recall status

# Reindexar tudo (troca de modelo, migração de dimensão)
total-recall index --full
```

### Skill `/recall` no Claude Code

Após `total-recall init`, a skill fica disponível em qualquer sessão:

| Comando | O que faz |
|---|---|
| `/recall <query>` | Busca e apresenta resultados no contexto (padrão: 8 resultados) |
| `/recall <query> --clip` | Busca + salva clipping em `~/.total-recall/clips/` |
| `/recall <query> --limit 15` | Mais resultados |
| `/recall <query> --session abc123` | Filtra por sessão específica |
| `/recall <query> --session abc123 --clip` | Filtra + salva clipping |

```
/recall o que decidimos sobre a arquitetura de memória?
/recall lancedb lancedb --clip
/recall banco vetorial decisão --session c3b0e47e --limit 15
```

O Claude executa `total-recall search` com a query, recebe os trechos mais relevantes em formato estruturado, e responde com base nas sessões recuperadas — com citação de sessão, data e contexto.

---

## Estrutura do Projeto

```
projetos/total-recall/
├── src/total_recall/
│   ├── config.py             # Constantes e variáveis de ambiente
│   ├── database.py           # Schema SQLite, WAL, sqlite-vec
│   ├── embeddings.py         # OllamaEmbedProvider (qwen3), OpenAIEmbedProvider
│   ├── models.py             # SessionInfo, Chunk, SearchResult, RecallContext
│   ├── vector_store.py       # Busca híbrida: vetorial + FTS5
│   ├── session_parser.py     # Parser JSONL → exchanges + blocos seletivos
│   ├── session_discovery.py  # Varredura de ~/.claude/projects/, delta SHA-256
│   ├── indexer.py            # Orquestração: discover → parse → embed → store
│   ├── recall_engine.py      # Temporal decay + role weights + MMR
│   ├── cold_export.py        # Exportação de sessão para Markdown
│   └── cli.py                # Interface Click
├── skill/
│   └── recall.md             # Definição da skill /recall para Claude Code
├── docs/
│   └── HANDOFF-*.md          # Documentos de decisão arquitetural
├── APRENDIZADOS.md           # Registro de descobertas técnicas por sessão
└── README.md
```

Runtime (criado por `total-recall init`):

```
~/.total-recall/
├── total-recall.db     # SQLite único (sessions, chunks, vec, fts, cache)
└── exports/            # Sessões exportadas em Markdown
```

---

## Configuração

Todas as configurações têm valores default razoáveis e podem ser sobrescritas via variáveis de ambiente:

```bash
TOTAL_RECALL_DATA=~/.total-recall          # Diretório de dados
TOTAL_RECALL_SESSIONS=~/.claude/projects   # Raiz dos JSONLs
TOTAL_RECALL_EMBED_PROVIDER=ollama         # Provedor: ollama | openai
TOTAL_RECALL_OLLAMA_MODEL=qwen3-embedding:4b
TOTAL_RECALL_EMBEDDING_DIMENSIONS=1024     # 1024 padrão; 2560 para máxima qualidade
TOTAL_RECALL_EMBED_USE_QUERY_INSTRUCTION=true
OPENAI_API_KEY=...                         # Apenas se provider=openai
```

---

## Notas sobre Escalabilidade

O sistema foi projetado para o volume típico de uso individual do Claude Code — na ordem de centenas a alguns milhares de sessões. Com 1024 dimensões e float32, cada chunk ocupa ~4 KB de vetor. Um corpus de 10.000 chunks gera ~40 MB de vetores, operando confortavelmente dentro das capacidades do SQLite com sqlite-vec.

Para corpora maiores, a primeira alavanca de otimização é a redução de dimensão (o Qwen3-Embedding suporta truncagem L2 sem degradação significativa até ~512 dims), antes de considerar backends alternativos.

---

## Referências e Inspiração

O design do pipeline de busca — busca híbrida vetor+BM25, MMR, temporal decay e sqlite-vec — converge com a arquitetura documentada pelo [OpenClaw](https://openclawlab.com/en/docs/concepts/memory/), que serviu como referência de validação durante o projeto. A implementação é independente: escrita em Python, específica para o formato de sessões do Claude Code CLI, e com extensões originais como exchange-based chunking, indexação seletiva de blocos internos (`thinking`/`tool_result`), decay com exceção para decisões arquiteturais, e role weights por tipo de conteúdo. Nenhum código foi derivado do OpenClaw.

---

*Projeto independente. Não tem vínculo com o Memória Viva — pode copiar padrões, nunca editar.*
