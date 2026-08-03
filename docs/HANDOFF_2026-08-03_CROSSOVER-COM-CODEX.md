# Handoff — Busca cruzada (crossover) com o total-recall-codex

**Data:** 2026-08-03
**Origem:** sessão no `total-recall-codex` (fork mais novo, Codex Desktop) que já implementou a metade espelhada disto (commit `67cd244`, "feat: busca cruzada (read-only) com o total-recall original")
**Objetivo:** dar ao `total-recall` (este projeto, Claude Code CLI) a capacidade simétrica de ler — só leitura, sob demanda — o banco do `total-recall-codex`, sem misturar os índices em disco.

O código do `total-recall-codex` é a fonte de verdade para "como isso já funciona do outro lado". Este documento mapeia cada peça dele para o arquivo equivalente aqui, apontando as diferenças estruturais que já existem entre os dois projetos e que a implementação precisa respeitar (não copiar cegamente).

---

## Prompt para colar numa sessão nova aqui no `total-recall`

```
Implemente busca cruzada (read-only) com o total-recall-codex, seguindo o
handoff em docs/HANDOFF_2026-08-03_CROSSOVER-COM-CODEX.md. Esse documento
mapeia exatamente o que mudar em cada arquivo, espelhando a implementação
que já existe e funciona no projeto irmão (total-recall-codex, commit
67cd244), com as adaptações de nomenclatura/timeout já identificadas lá.

Leia o handoff inteiro antes de começar — ele já resolveu as decisões de
design (nomes de env var, comportamento quando o banco irmão não existe,
como a fusão de resultados funciona). Não redesenhe do zero.

Ordem sugerida: config.py → database.py → models.py → recall_engine.py →
cli.py → skill/recall.md → README.md → testes → APRENDIZADOS.md.

Ao terminar, rode a suíte de testes e confirme manualmente com:
  total-recall search "<algo que sabe que só está no codex>" --source codex
  total-recall search "<algo que sabe que só está no codex>" --source both
```

---

## 1. Contexto: o que já existe do lado do codex

No `total-recall-codex`, `search --source {codex,claude-code,both}` permite:
- `codex` (padrão): só o banco isolado de sempre.
- `claude-code`: só o banco do `total-recall` original, aberto **read-only**.
- `both`: os dois, resultados fundidos por score em memória.

Peças-chave (todas em `src/total_recall_codex/`):
- `config.py` — `SIBLING_DB_PATH` (env `TOTAL_RECALL_CODEX_SIBLING_DB`, default `~/.total-recall/total-recall.db`).
- `database.py` — `Database.__init__(db_path, read_only=False)`. Se `read_only`, conecta via `sqlite3.connect(f"file:{path}?mode=ro", uri=True)` (bloqueio a nível de driver) e nunca chama `_init_db()`/`mkdir`. `transaction()` levanta `RuntimeError` se `read_only=True` — segunda camada de proteção redundante, mesmo que alguém tente escrever por engano.
- `models.py` — `SearchResult.origin: str = "codex"`, usado nas três funções de formatação (`format_rich`, `format_for_context`/`to_markdown`, `to_dict`) pra mostrar de qual banco veio cada resultado, e pra decidir a raiz do transcript original (`~/.codex/sessions` vs `~/.claude/projects`).
- `recall_engine.py` — `recall_cross(query, engines: dict[str, RecallEngine], limit, session_id)`: roda `.recall()` em cada engine do dict, marca `r.origin = <chave do dict>` em cada resultado, concatena, ordena por `score` desc, corta em `limit`. Os bancos nunca se tocam — a fusão é só na lista de `SearchResult` em memória.
- `cli.py` — `_build_sibling_engine()`: se `SIBLING_DB_PATH` não existe, retorna `None` (não é erro — "irmão não indexado ainda"). Senão monta `Database(read_only=True)` + `SQLiteVectorStore` + `RecallEngine` iguais aos do banco principal. O comando `search` ganha `--source` e ramifica nos 3 casos; no caso `both`, se o irmão não existir, avisa em stderr e segue só com o banco local (degrada graciosamente, não quebra).
- `skill/SKILL.md` — frases-gatilho dentro do texto livre: `buscar-no-claude-code` (força `--source claude-code`) e `cruzada`/`cross` (força `--source both`).

Sem teste dedicado a essa feature especificamente no repo do codex hoje (a suíte inteira passa, mas não há `test_crossover.py` isolado) — é uma lacuna que vale fechar aqui em vez de replicar.

---

## 2. Diferenças estruturais entre os dois projetos — não ignorar

Isso NÃO é um copy-paste 1:1. Pontos onde este projeto diverge do codex e a implementação precisa respeitar o que já existe aqui:

1. **Nome do pacote**: `total_recall`, não `total_recall_codex`. Os imports internos usam esse nome.
2. **`database.py:_get_connection` já tem `timeout=60.0`** no `sqlite3.connect()` do caminho de escrita (fix de lock contention entre hooks concorrentes, ver APRENDIZADOS.md item 53). O codex não tem esse timeout. **Preservar o `timeout=60.0` no ramo não-read-only** ao adicionar o ramo read-only — não overwrite a assinatura antiga.
3. **`SESSIONS_ROOT`** aqui é `~/.claude/projects` (não `~/.codex/sessions`) — isso já existe em `config.py`, não precisa mudar; só importa para a lógica de `transcript_root` em `models.py` quando `origin == "claude-code"` (self) vs `origin == "codex"` (sibling) — inverso do que está no código do codex.
4. **Nomenclatura do `--source` é invertida por perspectiva**: aqui, "eu" = `claude-code`, "o irmão" = `codex`. Sugestão de valores: `--source {claude-code (padrão), codex, both}`. Não reusar os mesmos rótulos do outro lado sem inverter o papel de default.
5. **Formatos de saída diferem**: aqui `search` tem `--format {rich,context,pointers,json}` (existe um formato `pointers` que o codex não tem) e usa `--output` em vez de `--clip`/`--force-color`. Adaptar o marcador de `origin` a esses formatos existentes, incluindo `format_pointers()` se ele expuser sessão/score.
6. **A skill `/recall` aqui delega para um sub-agente** (`Agent` tool, `subagent_type: general-purpose`) em vez de rodar a CLI e ler o resultado diretamente como no codex. O `--source` (ou as frases-gatilho equivalentes) precisa ser propagado para dentro do **template de prompt do sub-agente** em `skill/recall.md` (o comando `total-recall search ...` que o sub-agente executa), não só parseado no nível externo da skill.
7. **Env var**: por simetria de nome, use `TOTAL_RECALL_SIBLING_DB` (prefixo `TOTAL_RECALL_`, não `TOTAL_RECALL_CODEX_`), default `~/.total-recall-codex/total-recall-codex.db`.

---

## 3. Plano arquivo por arquivo

### `src/total_recall/config.py`
Adicionar, perto de `DB_PATH`/`SESSIONS_ROOT`:
```python
# Banco do "irmão mais novo" (total-recall-codex) para busca cruzada
# opcional (--source codex|both). Sempre aberto read-only — ver
# database.py Database(read_only=True). Ponte de LEITURA sob demanda,
# não um merge de índices.
SIBLING_DB_PATH = Path(os.getenv(
    "TOTAL_RECALL_SIBLING_DB",
    str(Path.home() / ".total-recall-codex" / "total-recall-codex.db"),
))
```

### `src/total_recall/database.py`
Espelhar o `__init__`/`_get_connection`/`transaction` do codex, **mantendo o `timeout=60.0` existente no ramo de escrita**:
```python
def __init__(self, db_path: Optional[Path] = None, read_only: bool = False):
    self.db_path = db_path or DB_PATH
    self.read_only = read_only
    if self.read_only:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Banco read-only não encontrado: {self.db_path}")
    else:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

def _get_connection(self) -> sqlite3.Connection:
    if self.read_only:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(self.db_path), timeout=60.0)  # preserva o fix existente
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn
```
E em `transaction()`, primeira linha: `if self.read_only: raise RuntimeError(...)`.

### `src/total_recall/models.py`
- `SearchResult.origin: str = "claude-code"` (default = self, não `"codex"` — inverso do codex).
- Nas três formatações (`format_rich`, `format_for_context`/markdown, `to_dict`/json): se `r.origin != "claude-code"`, anexar o marcador de origem na linha de metadata (mesmo padrão do codex: `sources_str += f" | {r.origin}"`).
- Onde existir lógica de raiz de transcript (se houver — conferir se `models.py` ou `cli.py` monta paths de export a partir de `session_id`): `transcript_root = "~/.codex/sessions" if r.origin == "codex" else "~/.claude/projects"`.

### `src/total_recall/recall_engine.py`
Portar `recall_cross()` praticamente sem mudanças — é agnóstica de projeto, só opera sobre `dict[str, RecallEngine]` e `SearchResult`.

### `src/total_recall/cli.py`
- `_build_sibling_engine()`: igual ao do codex, mas construindo `Database(db_path=SIBLING_DB_PATH, read_only=True)` + `SQLiteVectorStore` + `RecallEngine` com o `get_embedding_provider()` já usado aqui (conferir a assinatura atual antes de assumir que é idêntica à do codex — `search()` aqui já chama `get_embedding_provider()`, não monta o provider manualmente feito o `_build_engine()` do codex).
- `search`: acrescentar `@click.option("--source", type=click.Choice(["claude-code", "codex", "both"]), default="claude-code", ...)` e ramificar como no codex, adaptando para os formatos existentes (`rich`/`context`/`pointers`/`json`) em vez dos três do codex.
- Caso `both` sem banco irmão presente: aviso em stderr e segue só com o local — não travar o comando.

### `skill/recall.md`
- Adicionar ao bloco de flags suportadas: `buscar-no-codex` (força `--source codex`) e `cruzada`/`cross` (força `--source both`), seguindo o padrão de frases-gatilho do `SKILL.md` do codex.
- **Importante**: propagar isso para dentro do template do sub-agente (o bloco de comando `total-recall search "<cleaned query>" --format context --limit 8 [...]`), já que aqui quem roda a CLI é o sub-agente, não a skill diretamente.
- Adicionar instrução para o sub-agente mencionar a origem (`claude-code`/`codex`) de cada achado quando `--source` não for o padrão, espelhando o item 8 das instructions do `SKILL.md` do codex.

### `README.md`
Documentar `--source` e as frases-gatilho, espelhando a seção "Busca cruzada" do README do codex (linhas ~24 e ~61-68 lá).

### Testes
Não existe um `test_crossover.py` nem do lado do codex — criar um aqui (`tests/test_crossover.py`) cobrindo pelo menos:
- `Database(read_only=True)` levanta `FileNotFoundError` se o path não existe.
- `Database(read_only=True).transaction()` levanta `RuntimeError`.
- Conexão read-only realmente não consegue fazer `INSERT` (erro do próprio sqlite, não só da checagem em Python).
- `recall_cross()` funde e ordena por score corretamente com 2 engines fake/in-memory.
- `_build_sibling_engine()` retorna `None` quando o banco irmão não existe (sem lançar exceção).

### `APRENDIZADOS.md`
Registrar a entrada da feature ao final, no padrão já usado no arquivo (data + itens numerados + "Onde:").

---

## 4. Checklist de aceite

- [ ] `total-recall search "x" --source codex` lê só o banco do total-recall-codex, read-only de verdade (testar tentando escrever manualmente na conexão e confirmar erro do sqlite).
- [ ] `total-recall search "x" --source both` funde e ordena por score, sem duplicar nem misturar os bancos em disco.
- [ ] Banco irmão ausente → `both` degrada com aviso, não quebra; `codex` sozinho dá erro claro (banco não encontrado / não indexado nesta máquina).
- [ ] `timeout=60.0` do caminho de escrita local continua intacto.
- [ ] Skill `/recall` aceita `buscar-no-codex` e `cruzada`/`cross` dentro do texto livre e propaga pro sub-agente.
- [ ] Suíte de testes existente + novo `test_crossover.py` passam.
