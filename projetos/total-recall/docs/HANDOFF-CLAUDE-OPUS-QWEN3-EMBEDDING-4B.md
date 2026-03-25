# Handoff Técnico: Migrar Total Recall para `qwen3-embedding:4b`

## Objetivo

Atualizar o projeto **Total Recall** para usar **Ollama + `qwen3-embedding:4b`** como provedor padrão de embeddings, com foco em **melhor qualidade de busca e recuperação** para consultas em **pt-BR e inglês**.

Projeto-alvo:

- `/Users/criacao/Library/CloudStorage/OneDrive-Embelleze/MEUS-PROJETOS-IA/AGENTES/CLAUDE/projetos/total-recall`

Arquivos citados inicialmente:

- `/Users/criacao/Library/CloudStorage/OneDrive-Embelleze/MEUS-PROJETOS-IA/AGENTES/CLAUDE/projetos/total-recall/src/total_recall/config.py`
- `/Users/criacao/Library/CloudStorage/OneDrive-Embelleze/MEUS-PROJETOS-IA/AGENTES/CLAUDE/projetos/total-recall/src/total_recall/embeddings.py`

Importante: **ainda não existe índice gerado**. Portanto, é o momento correto para mudar modelo, dimensões e parâmetros sem custo de migração de dados antigos.

---

## Veredito

### Decisão principal

Usar:

- `provider = ollama`
- `model = qwen3-embedding:4b`
- `dimensions = 1024` (equilíbrio para busca híbrida vetor+FTS5)

### Fallback operacional

Se o `4b` ficar lento demais no M1 Pro 16 GB em uso real:

- fallback preferido: `qwen3-embedding:0.6b`
- não voltar para `nomic-embed-text` a menos que haja problema operacional real

### O que não fazer neste momento

- Não usar `all-minilm`
- Não usar `qwen3-embedding:8b` como padrão inicial
- Não manter o código preso semanticamente a `nomic`
- Não reduzir dimensão para `768` por compatibilidade histórica, porque ainda não há índice

---

## Racional Técnico

### 1. O melhor embedding para este caso é o Qwen

O projeto é uma memória pesquisável de conversas do Claude Code, com:

- texto técnico
- mistura de pt-BR e inglês
- perguntas semânticas do tipo "como decidimos X?"
- busca híbrida com vetor + keyword

Nesse cenário, o embedding precisa ser forte em:

- recuperação semântica
- multilíngue
- cross-lingual
- trechos técnicos e conversacionais

O `Qwen3-Embedding` é mais forte que `nomic-embed-text` para esse perfil. A família Qwen3 Embedding foi publicada com suporte a **100+ idiomas**, contexto longo, **instruction-aware**, e scores muito fortes em retrieval multilíngue. No benchmark MTEB multilingual publicado pela própria Qwen em junho de 2025:

- `Qwen3-Embedding-4B` marcou `69.45`
- `Qwen3-Embedding-8B` marcou `70.58`

Fonte:

- <https://github.com/QwenLM/Qwen3-Embedding>
- <https://ollama.com/library/qwen3-embedding:4b>

### 2. Por que o veredito não é simplesmente "seguir o default do OpenClaw"

Foi solicitado verificar o OpenClaw antes do veredito.

Conclusão:

- O OpenClaw usa busca híbrida BM25 + vetor
- mistura os scores
- aplica MMR para diversidade
- aplica recency boost / temporal decay
- acelera vetor com `sqlite-vec`

Fontes:

- <https://openclawlab.com/en/docs/concepts/memory/>
- `How we merge results (the current design)`
- `MMR re-ranking (diversity)`
- `Temporal decay (recency boost)`
- `SQLite vector acceleration (sqlite-vec)`

Isso importa porque, num sistema híbrido, o embedding não precisa "carregar tudo sozinho". BM25 já cobre:

- nomes exatos
- siglas
- tokens raros
- termos de código
- palavras-chave literais

Portanto, o embedding deve otimizar principalmente:

- semântica
- paráfrase
- consultas ambíguas
- português <-> inglês

Nesse ponto, `qwen3-embedding:4b` é a melhor escolha prática.

### 3. O OpenClaw usar `embeddinggemma` local e `nomic-embed-text` via Ollama não muda o veredito

O OpenClaw documenta:

- default local: `embeddinggemma`
- default Ollama: `nomic-embed-text`

Fontes:

- <https://openclawlab.com/en/docs/concepts/memory/>
- <https://raw.githubusercontent.com/openclaw/openclaw/main/src/memory/embeddings.ts>
- <https://raw.githubusercontent.com/openclaw/openclaw/main/src/memory/embeddings-ollama.ts>

Interpretação recomendada:

- isso é uma decisão de **default operacional seguro**
- não é evidência de melhor qualidade para o caso específico deste projeto

Para o Total Recall, o requisito declarado é **melhor resultado de busca e recuperação**, não menor atrito de instalação. Por isso, o veredito continua sendo `qwen3-embedding:4b`.

### 4. Por que usar `1024` dimensões (atualizado)

Decisão revisada após análise do uso real:

- O sistema usa busca **híbrida** (70% vetor + 30% FTS5), não vetor puro
- FTS5/BM25 já cobre keywords, siglas, termos de código
- O corpus é conversacional, não papers científicos
- Hardware: M1 Pro 16 GB — 1024 dims = ~4 KB/chunk vs 10 KB com 2560
- O ganho marginal de 2560 vs 1024 não compensa para este perfil

Recomendação implementada:

- `EMBEDDING_DIMENSIONS = 1024`

Ordem de fallback se necessário:

1. `qwen3-embedding:4b` + `1024` (default atual)
2. `qwen3-embedding:4b` + `2560` (se precisar de mais recall)
3. `qwen3-embedding:0.6b` + `1024` (se precisar de mais velocidade)

### 5. Por que não usar `qwen3-embedding:8b`

Porque o ganho incremental não compensa o custo inicial no hardware-alvo:

- `qwen3-embedding:4b` no Ollama: arquivo ~`2.5 GB`
- `qwen3-embedding:8b`: arquivo ~`4.7 GB`

No MacBook M1 Pro com 16 GB RAM:

- `4b` é uma escolha forte e viável
- `8b` entra mais fácil na zona de pressão de memória

Fontes:

- <https://ollama.com/library/qwen3-embedding:4b>
- <https://ollama.com/library/qwen3-embedding:8b>

---

## Decisões de Implementação

### Decisão 1: generalizar o provider de embedding

O código atual ainda está preso a `nomic`.

Hoje:

- `EMBED_PROVIDER` default = `"nomic"`
- `NOMIC_MODEL = "nomic-embed-text"`
- `EMBEDDING_DIMENSIONS = 768 if EMBED_PROVIDER == "nomic" else 1536`
- classe `NomicEmbedProvider`

Isso deve ser substituído por um desenho genérico baseado em `provider + model + dimensions`.

### Decisão 2: provider padrão deve ser `ollama`

Novo padrão:

- `TOTAL_RECALL_EMBED_PROVIDER=ollama`
- `TOTAL_RECALL_OLLAMA_MODEL=qwen3-embedding:4b`
- `TOTAL_RECALL_EMBEDDING_DIMENSIONS=1024`

### Decisão 3: query e document devem ser tratados de forma diferente

O Qwen recomenda instrução explícita para queries de retrieval.

O formato recomendado pela Qwen é algo na linha de:

```text
Instruct: Given a search query, retrieve relevant passages that answer the query.
Query: <consulta>
```

Fontes:

- <https://github.com/QwenLM/Qwen3-Embedding>

Aplicação recomendada no Total Recall:

- **queries**: usar instrução
- **documentos/chunks**: não usar instrução

Sugestão de instrução para este projeto:

```text
Instruct: Given a search query in Portuguese or English, retrieve relevant Claude Code conversation passages that answer the query.
Query: {query}
```

### Decisão 4: usar a API moderna de embedding do Ollama

Preferência:

- usar `ollama.embed(...)` se a versão do client suportar `dimensions`
- se houver incompatibilidade, usar `POST /api/embed` diretamente

Fonte:

- <https://docs.ollama.com/api/embed>

### Decisão 5: cache de embedding não pode depender só do texto

Hoje o `embedding_cache` usa `text_hash` como chave lógica, mas isso é insuficiente se o modelo ou a dimensão mudarem.

Mudança obrigatória:

- incluir `model` e `dimensions` na chave efetiva do cache
- ou, alternativamente, compor o hash com `model + dimensions + text`

Exemplo:

```text
sha256(f"{model}:{dimensions}:{text}")
```

Sem isso, haverá risco de reutilizar embedding errado após trocar modelo ou dimensão.

---

## Mudanças Obrigatórias no Código

## 1. `config.py`

Arquivo:

- `/Users/criacao/Library/CloudStorage/OneDrive-Embelleze/MEUS-PROJETOS-IA/AGENTES/CLAUDE/projetos/total-recall/src/total_recall/config.py`

### Substituir a configuração atual de embedding por algo deste tipo

```python
EMBED_PROVIDER = os.getenv("TOTAL_RECALL_EMBED_PROVIDER", "ollama")

OLLAMA_BASE_URL = os.getenv("TOTAL_RECALL_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_EMBED_MODEL = os.getenv("TOTAL_RECALL_OLLAMA_MODEL", "qwen3-embedding:4b")

EMBEDDING_DIMENSIONS = int(os.getenv("TOTAL_RECALL_EMBEDDING_DIMENSIONS", "2560"))

EMBED_QUERY_INSTRUCTION = os.getenv(
    "TOTAL_RECALL_EMBED_QUERY_INSTRUCTION",
    "Given a search query in Portuguese or English, retrieve relevant Claude Code conversation passages that answer the query."
)

EMBED_USE_QUERY_INSTRUCTION = os.getenv(
    "TOTAL_RECALL_EMBED_USE_QUERY_INSTRUCTION", "true"
).lower() == "true"
```

### Manter, mas desacoplar

Se quiser preservar provider OpenAI:

- manter `OPENAI_EMBED_MODEL`
- manter `OPENAI_API_KEY`

Mas `EMBEDDING_DIMENSIONS` não pode mais ser derivada de `provider == "nomic"`.

### Sugestão adicional

Adicionar:

```python
EMBED_BATCH_SIZE = int(os.getenv("TOTAL_RECALL_EMBED_BATCH_SIZE", "16"))
```

Mesmo que o provider atual não use batch de verdade, essa constante já prepara o desenho corretamente.

---

## 2. `embeddings.py`

Arquivo:

- `/Users/criacao/Library/CloudStorage/OneDrive-Embelleze/MEUS-PROJETOS-IA/AGENTES/CLAUDE/projetos/total-recall/src/total_recall/embeddings.py`

### Objetivos

1. Trocar `NomicEmbedProvider` por `OllamaEmbedProvider`
2. Tornar o provider independente do nome do modelo
3. Suportar `dimensions`
4. Suportar formatação diferente para query vs document

### Mudanças estruturais recomendadas

Alterar a interface para algo assim:

```python
class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        ...

    @abstractmethod
    def embed_document(self, text: str) -> list[float]:
        ...

    @abstractmethod
    def dimensions(self) -> int:
        ...

    @property
    def model_name(self) -> str:
        return "unknown"
```

### Novo provider Ollama

Implementar um provider com este comportamento:

- modelo configurável
- dimensão configurável
- query recebe instrução
- documento não recebe instrução
- vetores devem continuar normalizados, ou confiar na normalização do Ollama quando apropriado

Observação:

- a documentação do Ollama para `/api/embed` informa vetores L2-normalizados
- ainda assim, se o código atual já assume normalização explícita em algum ponto, manter coerência no pipeline

Fonte:

- <https://docs.ollama.com/capabilities/embeddings>
- <https://docs.ollama.com/api/embed>

### Formatação da query

Implementar helper:

```python
def format_query_for_embedding(query: str) -> str:
    return (
        "Instruct: Given a search query in Portuguese or English, "
        "retrieve relevant Claude Code conversation passages that answer the query.\n"
        f"Query: {query}"
    )
```

### Formatação do documento

Documento deve ir cru:

```python
def format_document_for_embedding(text: str) -> str:
    return text
```

### Compatibilidade com `ollama`

Prioridade:

1. usar `ollama.embed(model=..., input=..., dimensions=...)`
2. se a biblioteca local não suportar esse signature, fazer `POST /api/embed` com `requests`

Payload esperado:

```json
{
  "model": "qwen3-embedding:4b",
  "input": "texto ou array",
  "dimensions": 2560
}
```

### Teste de disponibilidade

No `get_embedding_provider()`:

- instanciar `OllamaEmbedProvider`
- testar com `embed_query("test")`
- retornar `None` apenas se realmente indisponível

### Preservar graceful degradation

Continuar aceitando:

- FTS5-only se Ollama não estiver disponível

Mas o comportamento padrão esperado para este projeto é com embedding ativo.

---

## 3. `database.py`

Arquivo:

- `/Users/criacao/Library/CloudStorage/OneDrive-Embelleze/MEUS-PROJETOS-IA/AGENTES/CLAUDE/projetos/total-recall/src/total_recall/database.py`

### Mudança necessária

O `vec0` deve usar a nova dimensão configurada:

```python
USING vec0(embedding float[{EMBEDDING_DIMENSIONS}])
```

Isso já existe conceitualmente, mas agora o valor default deve ser `2560`.

### Sugestão importante

Adicionar metadado explícito de dimensão/modelo no banco ou no cache para facilitar auditoria.

Opções:

1. adicionar `embed_dimensions INTEGER` em `chunks`
2. adicionar `dimensions INTEGER` em `embedding_cache`
3. gravar isso também em `metadata`

O mínimo aceitável é:

- `embedding_cache` registrar `model` e `dimensions`

---

## 4. `vector_store.py`

Arquivo provável:

- `/Users/criacao/Library/CloudStorage/OneDrive-Embelleze/MEUS-PROJETOS-IA/AGENTES/CLAUDE/projetos/total-recall/src/total_recall/vector_store.py`

### Mudanças obrigatórias

Hoje o cache de embedding provavelmente usa apenas o texto como identidade. Corrigir isso.

### Recomendação de API interna

- documentos indexados: chamar `embed_document(...)`
- query de busca: chamar `embed_query(...)`

Isso é importante para o Qwen, porque query e document não devem ser embedados exatamente da mesma forma.

### Sugestão adicional

Se houver oportunidade simples, centralizar a criação de embedding em um único método que receba:

- `text`
- `kind = "query" | "document"`

Isso reduz risco de divergência entre indexação e busca.

---

## 5. `cli.py`

Arquivo provável:

- `/Users/criacao/Library/CloudStorage/OneDrive-Embelleze/MEUS-PROJETOS-IA/AGENTES/CLAUDE/projetos/total-recall/src/total_recall/cli.py`

### Ajustes recomendados

No `init` e no `status`, exibir:

- provider atual
- modelo atual
- dimensões atuais
- disponibilidade do Ollama

Exemplo:

```text
Embedding: ollama / qwen3-embedding:4b (2560 dims)
```

### Mensagem de ajuda

Trocar dicas hardcoded de `nomic-embed-text` por algo genérico, por exemplo:

```text
Dica: instale o Ollama e rode `ollama pull qwen3-embedding:4b`
```

---

## Requisitos Funcionais

O resultado final deve cumprir estes requisitos:

1. O projeto deve iniciar normalmente com `qwen3-embedding:4b`
2. A dimensão default deve ser `2560`
3. Queries devem receber instrução; documentos não
4. `sqlite-vec` deve ser criado com a dimensão correta
5. O cache de embeddings não pode misturar modelos/dimensões diferentes
6. O sistema deve continuar funcionando em FTS-only se Ollama estiver offline
7. O output de status deve deixar claro qual modelo e dimensão estão ativos

---

## Requisitos Não Funcionais

1. Manter o design simples
2. Não introduzir dependência forte em `nomic`
3. Não acoplar a lógica a `768`
4. Não hardcodar nomes de modelo dentro de classes específicas
5. Preservar o padrão de graceful degradation

---

## Configuração Recomendada

### `.env` / variáveis de ambiente

```bash
TOTAL_RECALL_EMBED_PROVIDER=ollama
TOTAL_RECALL_OLLAMA_BASE_URL=http://127.0.0.1:11434
TOTAL_RECALL_OLLAMA_MODEL=qwen3-embedding:4b
TOTAL_RECALL_EMBEDDING_DIMENSIONS=1024
TOTAL_RECALL_EMBED_USE_QUERY_INSTRUCTION=true
TOTAL_RECALL_EMBED_QUERY_INSTRUCTION=Given a search query in Portuguese or English, retrieve relevant Claude Code conversation passages that answer the query.
```

### Instalação do modelo

```bash
ollama pull qwen3-embedding:4b
```

---

## Sugestões de Busca e Recuperação

Estas são recomendações adicionais. Implementar se o custo for baixo.

### 1. Manter o híbrido em `0.7 / 0.3`

O OpenClaw documenta o merge atual como:

- `vectorWeight = 0.7`
- `textWeight = 0.3`

Isso é uma base boa e já alinhada com o projeto.

Fonte:

- <https://openclawlab.com/en/docs/concepts/memory/>

### 2. Manter MMR com `lambda = 0.7`

Boa escolha inicial para reduzir redundância entre resultados.

### 3. Não aumentar chunk size agora

Manter inicialmente:

- `MAX_CHUNK_CHARS = 1500`
- `CHUNK_OVERLAP_CHARS = 200`

Razão:

- o projeto já usa exchange-based chunking
- a melhoria principal neste momento vem do embedding melhor
- mudar chunking e embedding ao mesmo tempo dificulta diagnóstico

### 4. Só testar redução de dimensão depois

Ordem de fallback recomendada:

1. `qwen3-embedding:4b` + `2560`
2. `qwen3-embedding:4b` + `1024`
3. `qwen3-embedding:0.6b` + `1024`
4. `qwen3-embedding:0.6b` + nativa
5. `embeddinggemma`

---

## Plano de Implementação Recomendado

1. Generalizar config de embedding
2. Implementar `OllamaEmbedProvider`
3. Separar `embed_query` de `embed_document`
4. Adicionar suporte a `dimensions`
5. Corrigir chave do cache
6. Ajustar CLI para exibir provider/model/dims
7. Atualizar README e mensagens de ajuda
8. Rodar validação end-to-end

---

## Validação Obrigatória

### Pré-requisitos

```bash
ollama pull qwen3-embedding:4b
```

### Verificações mínimas

1. `total-recall init`
   - deve detectar ou testar embedding com `qwen3-embedding:4b`

2. `total-recall status`
   - deve mostrar provider, modelo e dimensões corretos

3. `total-recall index --full`
   - deve indexar normalmente com embeddings

4. `total-recall search "como decidimos sobre sqlite-vec"`
   - deve retornar trechos semanticamente corretos

5. `total-recall search "what did we decide about vector storage"`
   - deve recuperar trechos relevantes mesmo que o conteúdo original esteja em português

6. desligar Ollama e repetir busca
   - o sistema deve cair para FTS-only sem quebrar

### Testes de regressão úteis

- query em pt-BR com documentos majoritariamente em inglês
- query em inglês com documentos majoritariamente em pt-BR
- query curta com termo técnico exato
- query abstrata tipo "qual foi a decisão de arquitetura"

---

## Critérios de Aceitação

Aceitar a mudança apenas se:

1. o modelo padrão for `qwen3-embedding:4b`
2. a dimensão default for `2560`
3. a busca usar query instruction
4. documentos não forem instruídos
5. o cache não misturar embeddings de modelos/dimensões diferentes
6. o projeto continuar funcionando sem Ollama em modo degradado
7. a CLI refletir claramente a nova configuração

---

## Observações Finais

### Decisão resumida

Se a meta é **melhor busca e recuperação**, a recomendação é:

- **usar `qwen3-embedding:4b`**

### Motivo resumido

- melhor qualidade multilíngue para pt-BR + inglês
- melhor ajuste para recall semântico em sistema híbrido
- ainda não existe índice legado para preservar
- o hardware consegue sustentar `4b` melhor do que `8b`

### Fallback resumido

Se o `4b` ficar pesado:

- trocar para `qwen3-embedding:0.6b`

Não retroceder para `nomic-embed-text` sem necessidade concreta.

---

## Fontes

- Ollama embeddings:
  - <https://docs.ollama.com/capabilities/embeddings>
  - <https://docs.ollama.com/api/embed>
- Ollama library:
  - <https://ollama.com/library/qwen3-embedding:4b>
  - <https://ollama.com/library/qwen3-embedding:0.6b>
  - <https://ollama.com/library/qwen3-embedding:8b>
  - <https://ollama.com/library/embeddinggemma>
  - <https://ollama.com/library/nomic-embed-text>
- Qwen:
  - <https://github.com/QwenLM/Qwen3-Embedding>
- OpenClaw:
  - <https://openclawlab.com/en/docs/concepts/memory/>
  - <https://raw.githubusercontent.com/openclaw/openclaw/main/src/memory/embeddings.ts>
  - <https://raw.githubusercontent.com/openclaw/openclaw/main/src/memory/embeddings-ollama.ts>
