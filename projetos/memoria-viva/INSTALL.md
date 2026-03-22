# Guia de Instalação — Memória Viva

## O que você vai precisar

| Requisito | O que é | Como instalar |
|---|---|---|
| Python 3.11+ | Linguagem de programação | Já vem no macOS ou `brew install python` |
| Ollama | Roda modelos de IA localmente | https://ollama.com → Download |
| Git | Controle de versão | Já vem no macOS |

## Passo a passo

### 1. Instalar o Ollama e baixar o modelo de embedding

O Ollama é o programa que roda o modelo de embedding na sua máquina.
Nenhum dado sai do computador — tudo é processado localmente.

```bash
# Baixa o modelo de embedding (768 dimensões, ~274 MB)
ollama pull nomic-embed-text

# Verifica se está funcionando (deve mostrar o modelo na lista)
ollama list
```

Se o Ollama não estiver rodando, inicie-o:

```bash
ollama serve
```

### 2. Criar ambiente virtual Python

Ambiente virtual isola as dependências deste projeto.
Não afeta nenhum outro programa no computador.

```bash
# Entra na pasta do projeto
cd projetos/memoria-viva

# Cria o ambiente virtual (uma vez só)
python3 -m venv .venv

# Ativa o ambiente virtual (fazer TODA VEZ que abrir o terminal)
source .venv/bin/activate

# No Windows:
# .venv\Scripts\activate
```

Quando o ambiente virtual está ativo, o terminal mostra `(.venv)` no início da linha.

### 3. Instalar o projeto

```bash
# Instala o projeto + dependências
pip install -e .

# Se quiser usar OpenAI como provedor de embedding (opcional):
# pip install -e ".[openai]"
```

O que o `pip install -e .` faz:
- Instala `sqlite-vec` (busca vetorial no SQLite)
- Instala `ollama` (cliente Python para o Ollama)
- Instala `click` (interface de linha de comando)
- Torna o comando `memoria-viva` disponível no terminal

### 4. Configurar o ambiente

```bash
# Copia o arquivo de exemplo
cp .env.example .env

# O padrão já funciona (nomic local, caminhos padrão).
# Só edite se precisar mudar algo.
```

### 5. Inicializar

```bash
# Cria o banco de dados e a estrutura de pastas
memoria-viva init
```

Deve mostrar:

```
Inicializando Memória Viva...

  Banco de dados: data/novex-memory.db
  Cold Store:     cold_store
  Embedding:      nomic-embed-text (768 dims) — OK

Memória Viva inicializada com sucesso!
```

### 6. Preencher o Código Genético

Edite o arquivo `cold_store/BRAND_MEMORY.md` com o Código Genético
da Novex/Embelleze (metodologia Ana Couto: É, FAZ e FALA).

Este arquivo é injetado em TODA execução — é a base de tudo.

## Verificar que tudo funciona

```bash
# Mostra o estado da memória
memoria-viva status

# Testa o memory read (deve mostrar contexto vazio, pois não há briefings)
memoria-viva memory-read "sérum de transição com quinoa"
```

## Comandos disponíveis

| Comando | O que faz |
|---|---|
| `memoria-viva init` | Inicializa banco + Cold Store |
| `memoria-viva status` | Mostra estado atual da memória |
| `memoria-viva search "texto"` | Busca na memória |
| `memoria-viva briefings` | Lista briefings registrados |
| `memoria-viva memory-read "ideia"` | Mostra contexto que seria injetado |
| `memoria-viva flush <id> GO -r "motivo"` | Executa Committee Flush |
| `memoria-viva bvs-real <id> 85.0` | Insere BVS Real |

## Estrutura de arquivos

```
projetos/memoria-viva/
├── src/memoria_viva/       ← Código Python (o "motor")
│   ├── config.py           ← Configurações (painel de controle)
│   ├── database.py         ← Banco de dados SQLite
│   ├── embeddings.py       ← Abstração de embedding (nomic/openai)
│   ├── vector_store.py     ← Busca vetorial (sqlite-vec + FTS5)
│   ├── cold_store.py       ← Operações no filesystem
│   ├── memory_manager.py   ← Agente 8 (o coração)
│   ├── models.py           ← Estruturas de dados
│   └── cli.py              ← Comandos do terminal
├── cold_store/             ← Memória legível por humanos
│   ├── BRAND_MEMORY.md     ← Código Genético (SEMPRE injetado)
│   ├── PM_CONTEXT.md       ← Contexto dos PMs
│   ├── MEMORY.md           ← Insights consolidados
│   ├── briefings/          ← Logs diários
│   └── segments/           ← Insights por segmento
├── data/
│   └── novex-memory.db     ← Banco SQLite (Hot + Warm Store)
├── pyproject.toml          ← Definição do projeto Python
├── .env.example            ← Template de configuração
└── INSTALL.md              ← Este arquivo
```

## Trocar de embedding provider

Para mudar de nomic (local) para OpenAI:

```bash
# 1. Edite o .env
EMBED_PROVIDER=openai
OPENAI_API_KEY=sk-...

# 2. Se já existem vetores no banco, PRECISA re-embedar:
#    (se o banco está vazio, não precisa — basta mudar o .env)
#    [Script de re-embedding será implementado no Estágio 3]
```

## Troubleshooting

| Problema | Solução |
|---|---|
| `ollama: command not found` | Instale o Ollama: https://ollama.com |
| `Error: model 'nomic-embed-text' not found` | Rode: `ollama pull nomic-embed-text` |
| `Connection refused` ao embedar | Rode: `ollama serve` |
| `OPENAI_API_KEY não configurada` | Defina no .env ou use `EMBED_PROVIDER=nomic` |
| `sqlite3.OperationalError: no such module: vec0` | Reinstale: `pip install sqlite-vec` |
