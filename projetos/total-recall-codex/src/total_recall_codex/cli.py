"""
cli.py — CLI do Total Recall Codex
===================================

Comandos:
  init        Instala a skill e cria diretórios
  index       Indexa sessões Codex
  search      Busca por query
  sessions    Lista sessões indexadas
  export      Exporta sessão para Markdown
  status      Mostra estatísticas
  doctor      Diagnóstico do sistema
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from .config import (
    DATA_DIR, DB_PATH, EXPORTS_PATH, SESSIONS_ROOT,
    OLLAMA_EMBED_MODEL, EMBED_PROVIDER, EMBEDDING_DIMENSIONS,
)
from .database import Database
from .embeddings import EmbeddingProvider, OllamaEmbedProvider
from .indexer import Indexer
from .recall_engine import RecallEngine
from .vector_store import SQLiteVectorStore
from .cold_export import ColdExporter


def _build_engine():
    """Constrói o pipeline completo (db + embeddings + vector store + recall)."""
    db = Database()
    provider: EmbeddingProvider | None = None
    if EMBED_PROVIDER == "ollama":
        provider = OllamaEmbedProvider(
            model=OLLAMA_EMBED_MODEL,
            dims=EMBEDDING_DIMENSIONS,
        )
    vector_store = SQLiteVectorStore(db, provider)
    return RecallEngine(db, vector_store), db, vector_store, provider


@click.group()
def main():
    """Total Recall Codex — Memória pesquisável para sessões do Codex."""
    pass


@main.command()
def init():
    """Instala a skill no Codex e cria diretórios."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_PATH.mkdir(parents=True, exist_ok=True)

    # Instala a skill
    skill_src = Path(__file__).parent.parent.parent / "skill" / "SKILL.md"
    skill_dst = Path.home() / ".codex" / "skills" / "recall" / "SKILL.md"

    if skill_src.exists():
        skill_dst.parent.mkdir(parents=True, exist_ok=True)
        skill_dst.write_text(skill_src.read_text(), encoding="utf-8")
        click.echo(f"  Skill instalada: {skill_dst}")
    else:
        click.echo(f"  AVISO: skill/SKILL.md não encontrado em {skill_src}")
        click.echo(f"  Instale manualmente em: {skill_dst}")

    click.echo(f"  Data dir: {DATA_DIR}")
    click.echo(f"  Sessions root: {SESSIONS_ROOT}")
    click.echo("")
    click.echo("Pronto. Rode 'total-recall-codex index' para indexar.")


@main.command()
@click.option("--full", is_flag=True, help="Reindexação completa (ignora cache)")
@click.option("--session", multiple=True, help="Indexa apenas session IDs específicos")
def index(full, session):
    """Indexa sessões Codex no banco."""
    engine, db, vector_store, provider = _build_engine()
    indexer = Indexer(db, vector_store, embed_provider=provider)

    session_ids = list(session) if session else None

    click.echo(f"Indexando sessões Codex em {SESSIONS_ROOT}...")
    click.echo(f"  Embedding: {EMBED_PROVIDER} / {OLLAMA_EMBED_MODEL} ({EMBEDDING_DIMENSIONS} dims)")
    click.echo("")

    result = indexer.index_all(full=full, session_ids=session_ids)

    click.echo(f"  Arquivos escaneados: {result['files_scanned']}")
    click.echo(f"  Arquivos indexados: {result['files_indexed']}")
    click.echo(f"  Chunks criados:     {result['chunks_created']}")

    if result.get("errors"):
        click.echo(f"  Erros: {len(result['errors'])}")
        for err in result["errors"][:5]:
            click.echo(f"    - {err}")

    click.echo("")
    click.echo("Indexação concluída.")


@main.command()
@click.argument("query")
@click.option("--limit", default=5, help="Número de resultados")
@click.option("--session", default=None, help="Filtra por session ID (prefixo)")
@click.option("--format", "fmt", default="context", type=click.Choice(["context", "json"]))
@click.option("--clip", is_flag=True, help="Salva resultados em clip datado")
def search(query, limit, session, fmt, clip):
    """Busca por query semântica ou keyword."""
    engine, db, _, _ = _build_engine()

    ctx = engine.recall(query, limit=limit, session_id=session)

    if fmt == "json":
        click.echo(json.dumps(ctx.to_dict(), indent=2, ensure_ascii=False))
        return

    if not ctx.results:
        click.echo(f"Nenhum resultado para: \"{query}\"")
        click.echo(f"  ({ctx.sessions_searched} sessões, {ctx.total_chunks} chunks indexados)")
        if ctx.query_info.get("search_mode"):
            click.echo(f"  Modo: {ctx.query_info['search_mode']}")
        return

    click.echo(f"## Resultados para: \"{query}\"")
    click.echo(f"*{len(ctx.results)} resultados de {ctx.sessions_searched} sessões indexadas*")

    if ctx.query_info.get("expansions"):
        exp_parts = []
        for exp in ctx.query_info["expansions"]:
            if exp["type"] == "abbreviation":
                exp_parts.append(f"abbrev: {exp['original']} → {', '.join(exp['expanded'])}")
            elif exp["type"] == "fuzzy":
                exp_parts.append(f"fuzzy: {exp['original']} → {', '.join(exp['expanded'])}")
        if exp_parts:
            click.echo(f"\n*Expansões: {'; '.join(exp_parts)}*")

    for i, r in enumerate(ctx.results, 1):
        sources = " + ".join(s.upper() for s in r.sources) if r.sources else "?"
        click.echo("")
        click.echo(f"### {i}. {r.project_label or r.session_id[:8]} — Sessão {r.session_id[:8]}")
        ts = r.timestamp.strftime("%d/%m/%Y %H:%M") if r.timestamp else "?"
        click.echo(f"*Sessão `{r.session_id[:8]}` | {ts} | score: {r.score:.3f} | {sources}*")
        click.echo("")
        click.echo(r.content)

    if clip:
        clips_dir = Path.home() / ".total-recall-codex" / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        clip_path = clips_dir / f"clip-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
        clip_path.write_text(ctx.to_markdown(), encoding="utf-8")
        click.echo(f"\nClip salvo: {clip_path}")


@main.command()
@click.option("--limit", default=20, help="Máximo de sessões")
@click.option("--project", default=None, help="Filtra por projeto")
def sessions(limit, project):
    """Lista sessões indexadas."""
    db = Database()
    with db.connection() as conn:
        sql = "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?"
        params: list = [limit]
        if project:
            sql = "SELECT * FROM sessions WHERE project_label LIKE ? ORDER BY started_at DESC LIMIT ?"
            params = [f"%{project}%", limit]

        rows = conn.execute(sql, params).fetchall()

    if not rows:
        click.echo("Nenhuma sessão indexada.")
        return

    click.echo(f"## {len(rows)} sessões indexadas")
    click.echo("")
    for row in rows:
        ts = row["started_at"] or "?"
        project = row["project_label"] or "?"
        click.echo(f"- `{row['session_id'][:8]}` | {ts} | {project} | {row['user_messages']}u/{row['asst_messages']}a")


@main.command()
@click.argument("session_id")
def export(session_id):
    """Exporta sessão para Markdown."""
    db = Database()
    exporter = ColdExporter(db)
    path = exporter.export_session(session_id)
    if path:
        click.echo(f"Exportado: {path}")
    else:
        click.echo(f"Sessão não encontrada: {session_id}")


@main.command()
def status():
    """Mostra estatísticas do banco."""
    db = Database()
    with db.connection() as conn:
        sessions_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        chunks_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        chunks_with_emb = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE has_embedding = 1"
        ).fetchone()[0]
        cache_count = conn.execute(
            "SELECT COUNT(*) FROM embedding_cache"
        ).fetchone()[0]
        last_run = conn.execute(
            "SELECT * FROM indexing_runs ORDER BY ended_at DESC LIMIT 1"
        ).fetchone()

    click.echo("Total Recall Codex — Status")
    click.echo("")
    click.echo(f"  Banco: {DB_PATH} ({DB_PATH.stat().st_size / 1024 / 1024:.2f} MB)")
    click.echo(f"  Sessões indexadas: {sessions_count}")
    click.echo(f"  Chunks: {chunks_count} ({chunks_with_emb} com embedding)")
    click.echo(f"  Cache de embeddings: {cache_count} entradas")

    if last_run:
        click.echo(f"  Última indexação: {last_run['ended_at']} ({last_run['files_indexed']} arquivos, {last_run['chunks_created']} chunks)")

    click.echo(f"  Embedding: {EMBED_PROVIDER} / {OLLAMA_EMBED_MODEL} ({EMBEDDING_DIMENSIONS} dims)")

    jsonl_count = len(list(SESSIONS_ROOT.glob("**/*.jsonl"))) if SESSIONS_ROOT.exists() else 0
    click.echo(f"  Sessões JSONL disponíveis: {jsonl_count}")


@main.command()
def doctor():
    """Diagnóstico do sistema."""
    issues = []

    # Check data dir
    if not DATA_DIR.exists():
        issues.append(f"Data dir não existe: {DATA_DIR}")

    # Check DB
    if DB_PATH.exists():
        db = Database()
        with db.connection() as conn:
            sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            if sessions == 0:
                issues.append("Banco existe mas está vazio — rode 'total-recall-codex index'")
    else:
        issues.append("Banco não existe — rode 'total-recall-codex init'")

    # Check sessions root
    if not SESSIONS_ROOT.exists():
        issues.append(f"Sessions root não existe: {SESSIONS_ROOT}")
    else:
        jsonl_count = len(list(SESSIONS_ROOT.glob("**/*.jsonl")))
        if jsonl_count == 0:
            issues.append(f"Nenhum JSONL encontrado em {SESSIONS_ROOT}")

    # Check Ollama
    try:
        import ollama
        client = ollama.Client()
        client.list()
    except Exception:
        issues.append("Ollama não está respondendo em http://127.0.0.1:11434")

    # Check skill
    skill_path = Path.home() / ".codex" / "skills" / "recall" / "SKILL.md"
    if not skill_path.exists():
        issues.append(f"Skill não instalada — rode 'total-recall-codex init'")

    if issues:
        click.echo("Total Recall Codex — Diagnóstico")
        click.echo("")
        for issue in issues:
            click.echo(f"  ⚠ {issue}")
        click.echo("")
        click.echo(f"  {len(issues)} problema(s) encontrado(s).")
    else:
        click.echo("Total Recall Codex — Diagnóstico")
        click.echo("")
        click.echo("  ✓ Tudo OK")


if __name__ == "__main__":
    main()
