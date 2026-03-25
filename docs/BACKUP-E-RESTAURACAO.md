# Backup e Restauração — Total Recall

> Guia técnico de alto nível para backup, restauração e migração do banco
> de dados do Total Recall. Cobre fundamentos do SQLite em WAL mode,
> cenários de falha, estratégias de backup seguro e procedimentos de
> recuperação entre máquinas.

---

## Arquitetura de Persistência

Antes de qualquer procedimento de backup, é essencial compreender o que
precisa ser preservado e por quê.

### O que o Total Recall armazena

O sistema mantém dois tipos de dado com naturezas distintas:

**Dado derivado** — tudo que está em `~/.total-recall/`:

```
~/.total-recall/
├── total-recall.db      ← banco SQLite principal
└── exports/             ← sessões exportadas em Markdown (opcional)
```

O banco é *derivado*: foi construído a partir dos JSONLs originais em
`~/.claude/projects/`. Isso tem uma implicação fundamental: **se o banco
for perdido ou corrompido, pode ser reconstruído do zero** com:

```bash
total-recall index --full
```

**Dado primário** — os JSONLs em `~/.claude/projects/`:

```
~/.claude/projects/
└── <project-dir>/
    └── <session-id>.jsonl    ← fonte de verdade, gerida pelo Claude Code
```

Esses arquivos não são de responsabilidade do Total Recall — são criados e
geridos pelo Claude Code CLI. O Total Recall os lê, nunca os modifica.

### Consequência prática

A questão de backup tem duas respostas diferentes dependendo do que você
quer proteger:

| O que proteger | Estratégia |
|---|---|
| As conversas em si | Backup dos JSONLs em `~/.claude/projects/` |
| O índice (velocidade de busca) | Backup do `total-recall.db` |
| Os embeddings (tempo de reindexação) | Backup do `total-recall.db` (inclui cache) |

Se os JSONLs estiverem íntegros, o banco pode sempre ser recriado. O banco
é um investimento de tempo de processamento, não um dado insubstituível.

---

## SQLite em WAL Mode — O que Significa para Backup

O Total Recall opera o banco em **WAL mode** (Write-Ahead Log). Entender
esse mecanismo é pré-requisito para fazer backup correto.

### Como o WAL funciona

No modo padrão do SQLite (rollback journal), toda escrita modifica o arquivo
principal diretamente, com um journal temporário para rollback em caso de falha.
No WAL mode, o comportamento é invertido: escritas vão para um arquivo separado
(`total-recall.db-wal`), e o arquivo principal é atualizado periodicamente num
processo chamado *checkpoint*.

```
total-recall.db       ← estado "commitado" (pode estar atrasado)
total-recall.db-wal   ← escritas recentes não checkpointed
total-recall.db-shm   ← memória compartilhada de coordenação (gerado automaticamente)
```

O banco de dados completo e consistente é a combinação dos três arquivos.
Copiar apenas `total-recall.db` sem os arquivos `-wal` e `-shm` pode resultar
em um backup incompleto ou inconsistente.

### Implicação para cópia simples de arquivo

Uma cópia ingênua com `cp total-recall.db backup.db` é **potencialmente
insegura** se houver um processo usando o banco no momento da cópia. Os
arquivos WAL e SHM devem ser copiados em conjunto, ou deve-se usar um método
que produza um snapshot consistente (ver seções abaixo).

---

## Métodos de Backup

### Método 1 — Backup via SQLite Online (recomendado)

O SQLite possui um mecanismo nativo de backup online que produz um snapshot
consistente mesmo com o banco em uso. É a abordagem mais segura.

```bash
# Usando sqlite3 CLI
sqlite3 ~/.total-recall/total-recall.db ".backup ~/.total-recall/total-recall-backup.db"
```

Ou via Python (mais controlável):

```python
import sqlite3
import sqlite_vec

src = sqlite3.connect(str(db_path))
src.enable_load_extension(True)
sqlite_vec.load(src)
src.enable_load_extension(False)

dst = sqlite3.connect(str(backup_path))
src.backup(dst)
dst.close()
src.close()
```

**Como funciona**: o método `backup()` do Python utiliza a SQLite Backup API,
que lê o banco página a página com locks mínimos, garantindo consistência
mesmo durante operações de escrita concorrentes. O resultado é um arquivo
`.db` independente, sem `-wal` ou `-shm` associados.

**Quando usar**: qualquer situação onde o banco pode estar em uso — o método
mais seguro para automação.

### Método 2 — Cópia de arquivo com banco fechado

Se garantir que nenhum processo está usando o banco (sem `total-recall`
em execução, sem Ollama indexando), uma cópia de arquivo simples é segura —
desde que inclua todos os três arquivos:

```bash
# Garantir que não há processos ativos
pkill -f total-recall 2>/dev/null || true

# Copiar todos os arquivos do banco
cp ~/.total-recall/total-recall.db       ~/backups/total-recall.db
cp ~/.total-recall/total-recall.db-wal   ~/backups/total-recall.db-wal   2>/dev/null || true
cp ~/.total-recall/total-recall.db-shm   ~/backups/total-recall.db-shm   2>/dev/null || true
```

Os arquivos `-wal` e `-shm` podem não existir se o banco foi checkpointed
recentemente — isso é normal e esperado.

**Quando usar**: backup manual pontual, antes de operações destrutivas como
`--full` reindex.

### Método 3 — Forçar checkpoint antes da cópia

Para garantir que o arquivo `.db` principal esteja completamente atualizado
antes da cópia (eliminando dependência dos arquivos WAL):

```bash
sqlite3 ~/.total-recall/total-recall.db "PRAGMA wal_checkpoint(FULL);"
cp ~/.total-recall/total-recall.db ~/backups/total-recall.db
```

O `PRAGMA wal_checkpoint(FULL)` força a escrita de todas as entradas WAL
pendentes no arquivo principal e aguarda a conclusão. Após isso, o arquivo
`.db` contém o estado completo e pode ser copiado com segurança.

---

## O que Fazer Antes de Operações Destrutivas

Certas operações do Total Recall são irreversíveis. O procedimento de
precaução é sempre o mesmo:

```bash
# 1. Backup do banco atual
sqlite3 ~/.total-recall/total-recall.db \
  ".backup ~/.total-recall/total-recall-pre-full-$(date +%Y%m%d).db"

# 2. Executar a operação destrutiva
total-recall index --full

# 3. Verificar integridade do novo banco
total-recall status
```

**Operações que exigem backup prévio**:

| Operação | Por quê |
|---|---|
| `total-recall index --full` | Apaga todos os chunks, vetores, sessões e cache |
| Trocar modelo de embedding | Requer `--full`; invalida todos os embeddings existentes |
| Mudar `EMBEDDING_DIMENSIONS` | Requer recriação da tabela vec0; dados incompatíveis |
| Migrar entre máquinas | Banco pode ter paths absolutos de sessões diferentes |

---

## Verificação de Integridade

Após qualquer backup ou restauração, verificar:

```bash
# Verificação básica de integridade do SQLite
sqlite3 ~/.total-recall/total-recall.db "PRAGMA integrity_check;"
# Saída esperada: ok

# Verificação de consistência das tabelas
sqlite3 ~/.total-recall/total-recall.db "
  SELECT
    (SELECT COUNT(*) FROM sessions)  AS sessions,
    (SELECT COUNT(*) FROM chunks)    AS chunks,
    (SELECT COUNT(*) FROM chunks_vec) AS chunks_vec,
    (SELECT COUNT(*) FROM chunks_fts) AS chunks_fts;
"
# chunks, chunks_vec e chunks_fts devem ter o mesmo valor

# Via CLI do Total Recall
total-recall status
```

Uma inconsistência entre `chunks` e `chunks_vec` indica que o backup foi
feito com o banco em estado parcialmente escrito. Nesse caso, reconstruir
com `total-recall index --full`.

---

## Restauração

### Restauração simples (mesmo dispositivo)

```bash
# Parar qualquer processo usando o banco
pkill -f total-recall 2>/dev/null || true

# Substituir pelo backup
cp ~/backups/total-recall-backup.db ~/.total-recall/total-recall.db

# Remover arquivos WAL/SHM residuais (se existirem)
rm -f ~/.total-recall/total-recall.db-wal
rm -f ~/.total-recall/total-recall.db-shm

# Verificar
total-recall status
```

### Restauração completa (banco corrompido ou perdido)

Se o banco foi perdido mas os JSONLs estão íntegros:

```bash
# Recriar o banco do zero a partir dos JSONLs originais
total-recall init
total-recall index --full
```

O processo reindexada todas as sessões disponíveis em `~/.claude/projects/`.
O tempo depende do número de sessões e da disponibilidade do Ollama para
gerar embeddings. Sem Ollama, o sistema opera em modo FTS5-only e a indexação
é instantânea; embeddings podem ser gerados depois quando o Ollama estiver
disponível.

---

## Migração entre Máquinas

O Total Recall foi projetado para uso local em dispositivo único. A migração
entre máquinas (ex: Mac para Windows, ou Mac pessoal para Mac do trabalho)
envolve considerações específicas.

### O que migrar

```
Origem (~/)                          Destino (~/)
~/.total-recall/total-recall.db  →  ~/.total-recall/total-recall.db
~/.claude/projects/               →  ~/.claude/projects/   (gerido pelo Claude Code)
~/.local/bin/total-recall         →  ~/.local/bin/total-recall
~/.claude/commands/recall.md      →  ~/.claude/commands/recall.md
```

### Problema: paths absolutos

O banco armazena o caminho absoluto de cada arquivo JSONL indexado na coluna
`file_path` da tabela `sessions`. Se o caminho muda entre máquinas (comum
entre Mac e Windows, ou entre usuários diferentes), o banco importado terá
paths incorretos e o delta indexing falhará silenciosamente.

**Sintoma**: `total-recall index` reporta todos os arquivos como novos e
reindexada tudo mesmo que não tenha mudado nada.

**Solução recomendada**: ao migrar, executar `total-recall index --full`
na máquina de destino após copiar os JSONLs. Isso reconstrói o banco com
os paths corretos da nova máquina. O banco copiado não é diretamente
utilizável se os paths mudaram.

**Alternativa**: migrar sem o banco e reconstruir do zero. Como o banco é
derivado, não há perda de informação — apenas tempo de processamento.

### Migração de JSONLs com OneDrive/sincronização

Se os JSONLs estão sincronizados via OneDrive (como neste setup), o processo
é simplificado:

```bash
# Na máquina de destino, após sincronização dos JSONLs:
total-recall init
TOTAL_RECALL_SESSIONS=/caminho/onedrive/.claude/projects total-recall index --full
```

O `TOTAL_RECALL_SESSIONS` permite apontar para o diretório correto se o
`.claude/projects/` não estiver no path padrão `~/.claude/projects/`.

---

## Automação de Backup

### Script de backup diário (macOS/launchd ou cron)

```bash
#!/bin/bash
# backup-total-recall.sh

BACKUP_DIR="$HOME/Library/Mobile Documents/com~apple~CloudDocs/backups/total-recall"
DB="$HOME/.total-recall/total-recall.db"
DATE=$(date +%Y%m%d)
DEST="$BACKUP_DIR/total-recall-$DATE.db"

mkdir -p "$BACKUP_DIR"

# Backup online via SQLite API (seguro mesmo com banco em uso)
sqlite3 "$DB" ".backup $DEST"

# Manter apenas os últimos 7 backups
ls -t "$BACKUP_DIR"/total-recall-*.db | tail -n +8 | xargs rm -f 2>/dev/null

echo "Backup: $DEST"
```

### Via cron

```cron
# Backup diário às 02:00
0 2 * * * /path/to/backup-total-recall.sh >> /tmp/total-recall-backup.log 2>&1
```

---

## Resumo das Boas Práticas

| Situação | Ação |
|---|---|
| Antes de `--full` reindex | Backup com `.backup` do sqlite3 |
| Antes de trocar modelo de embedding | Backup + documentar versão anterior |
| Banco corrompido (integrity_check falha) | Deletar e reconstruir com `--full` |
| Migração entre máquinas | Copiar JSONLs; reconstruir banco na destino |
| Backup rotineiro | Script automático + `.backup` online |
| Verificação pós-restauração | `PRAGMA integrity_check` + `total-recall status` |

---

## Referências Técnicas

- [SQLite WAL Mode](https://www.sqlite.org/wal.html) — documentação oficial do mecanismo WAL
- [SQLite Backup API](https://www.sqlite.org/backup.html) — API de backup online
- [sqlite3.Connection.backup()](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup) — binding Python
- [sqlite-vec](https://github.com/asg017/sqlite-vec) — extensão vetorial usada no projeto
