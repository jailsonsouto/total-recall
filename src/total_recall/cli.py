"""
cli.py — Interface de linha de comando do Total Recall
"""

import json
import sys
import shutil
from datetime import datetime
from pathlib import Path

import click

from .config import DATA_DIR, DB_PATH, EXPORTS_PATH, SESSIONS_ROOT
from .database import Database
from .embeddings import get_embedding_provider


@click.group()
def main():
    """Total Recall — Memória pesquisável para sessões do Claude Code."""
    pass


@main.command()
def init():
    """Inicializa o banco de dados, diretórios e instala a skill /recall."""
    click.echo("Inicializando Total Recall...\n")

    # 1. Cria diretórios
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_PATH.mkdir(parents=True, exist_ok=True)
    click.echo(f"  Diretório de dados: {DATA_DIR}")

    # 2. Inicializa banco
    db = Database()
    click.echo(f"  Banco de dados: {DB_PATH}")

    # 3. Testa embedding
    provider = get_embedding_provider()
    if provider:
        click.echo(f"  Embedding: {provider.model_name} ({provider.dimensions()} dims)")
    else:
        click.echo("  Embedding: INDISPONIVEL (FTS5-only mode)")
        click.echo("    Dica: instale Ollama e rode 'ollama pull nomic-embed-text'")

    # 4. Verifica sessões
    if SESSIONS_ROOT.exists():
        jsonl_count = sum(1 for _ in SESSIONS_ROOT.rglob("*.jsonl"))
        click.echo(f"  Sessões encontradas: {jsonl_count} arquivos JSONL em {SESSIONS_ROOT}")
    else:
        click.echo(f"  Sessões: diretório não encontrado ({SESSIONS_ROOT})")

    # 5. Instala skill
    skill_src = Path(__file__).parent.parent.parent / "skill" / "recall.md"
    skill_dst = Path.home() / ".claude" / "commands" / "recall.md"
    if skill_src.exists():
        skill_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skill_src, skill_dst)
        click.echo(f"  Skill /recall instalada: {skill_dst}")
    else:
        click.echo("  Skill /recall: arquivo fonte não encontrado (instale manualmente)")

    click.echo("\nTotal Recall inicializado com sucesso!")
    click.echo("Próximo passo: total-recall index")


@main.command()
def status():
    """Mostra estado do sistema."""
    click.echo("Total Recall — Status\n")

    # DB
    if DB_PATH.exists():
        size_mb = DB_PATH.stat().st_size / (1024 * 1024)
        click.echo(f"  Banco: {DB_PATH} ({size_mb:.2f} MB)")

        db = Database()
        with db.connection() as conn:
            sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            cached = conn.execute("SELECT COUNT(*) FROM embedding_cache").fetchone()[0]
            with_emb = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE has_embedding = TRUE"
            ).fetchone()[0]

            click.echo(f"  Sessões indexadas: {sessions}")
            click.echo(f"  Chunks: {chunks} ({with_emb} com embedding)")
            click.echo(f"  Cache de embeddings: {cached} entradas")

            # Última indexação
            last_run = conn.execute(
                "SELECT * FROM indexing_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if last_run:
                click.echo(
                    f"  Última indexação: {last_run['started_at']} "
                    f"({last_run['files_indexed']} arquivos, "
                    f"{last_run['chunks_created']} chunks)"
                )
    else:
        click.echo(f"  Banco: não inicializado. Rode 'total-recall init'")

    # Embedding
    provider = get_embedding_provider()
    if provider:
        click.echo(f"  Embedding: {provider.model_name} (OK)")
    else:
        click.echo("  Embedding: INDISPONIVEL (modo FTS5-only)")

    # Sessões disponíveis
    if SESSIONS_ROOT.exists():
        jsonl_count = sum(1 for _ in SESSIONS_ROOT.rglob("*.jsonl"))
        click.echo(f"  Sessões JSONL disponíveis: {jsonl_count}")


@main.command()
@click.option("--full", is_flag=True, help="Reindexar tudo (ignora hashes)")
@click.option("--subagents/--no-subagents", default=False,
              help="Incluir sessões de subagentes")
def index(full, subagents):
    """Indexa sessões (incremental por padrão)."""
    from .indexer import Indexer
    from .session_discovery import SessionDiscovery
    from .vector_store import SQLiteVectorStore

    db = Database()
    provider = get_embedding_provider()
    vector_store = SQLiteVectorStore(db, provider)
    discovery = SessionDiscovery(SESSIONS_ROOT, db, include_subagents=subagents)

    indexer = Indexer(db, vector_store, provider, discovery)
    report = indexer.index(full=full)

    click.echo(f"\nIndexação concluída!")
    click.echo(f"  Arquivos escaneados: {report['files_scanned']}")
    click.echo(f"  Arquivos indexados: {report['files_indexed']}")
    click.echo(f"  Arquivos ignorados: {report['files_skipped']}")
    click.echo(f"  Chunks criados: {report['chunks_created']}")
    if report['errors']:
        click.echo(f"  Erros: {len(report['errors'])}")
        for err in report['errors'][:5]:
            click.echo(f"    - {err}")


@main.command()
@click.argument("query")
@click.option("--limit", "-n", default=5, help="Número de resultados")
@click.option("--session", "-s", default=None, help="Filtrar por session ID")
@click.option("--format", "-f", "fmt",
              type=click.Choice(["rich", "context", "json"]),
              default="rich", help="Formato de saída")
def search(query, limit, session, fmt):
    """Busca em todas as sessões indexadas."""
    from .recall_engine import RecallEngine
    from .vector_store import SQLiteVectorStore

    db = Database()
    provider = get_embedding_provider()
    vector_store = SQLiteVectorStore(db, provider)
    engine = RecallEngine(db, vector_store)

    ctx = engine.recall(query, limit=limit, session_id=session)

    if fmt == "context":
        click.echo(ctx.format_for_context())
    elif fmt == "json":
        import json
        results = []
        for r in ctx.results:
            results.append({
                "content": r.content,
                "session_id": r.session_id,
                "session_title": r.session_title,
                "project": r.project_label,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "score": r.score,
                "role": r.role,
            })
        click.echo(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        # rich (default)
        if not ctx.results:
            click.echo(f"Nenhum resultado para: \"{query}\"")
            return

        click.echo(f"Resultados para: \"{query}\" ({len(ctx.results)} encontrados)\n")
        for i, r in enumerate(ctx.results, 1):
            ts = r.timestamp.strftime("%d/%m/%Y %H:%M") if r.timestamp else "?"
            click.echo(f"  [{i}] {r.project_label} — {r.session_title}")
            click.echo(f"      Sessão {r.session_id[:8]} | {ts} | score: {r.score:.3f}")
            # Mostra trecho (primeiros 300 chars)
            preview = r.content[:300].replace("\n", " ")
            if len(r.content) > 300:
                preview += "..."
            click.echo(f"      {preview}")
            click.echo()


@main.command()
@click.option("--project", "-p", default=None, help="Filtrar por projeto")
def sessions(project):
    """Lista sessões indexadas."""
    db = Database()
    with db.connection() as conn:
        query = "SELECT * FROM sessions ORDER BY started_at DESC"
        rows = conn.execute(query).fetchall()

        if not rows:
            click.echo("Nenhuma sessão indexada. Rode 'total-recall index'")
            return

        for row in rows:
            if project and project.lower() not in (row["project_label"] or "").lower():
                continue
            started = row["started_at"] or "?"
            title = row["title"] or "(sem título)"
            click.echo(
                f"  {row['session_id'][:8]}  {started}  "
                f"{row['project_label']:20s}  {title}"
            )
            click.echo(
                f"           {row['user_messages']} user + "
                f"{row['asst_messages']} assistant msgs"
            )


@main.command()
@click.argument("session_id")
def export(session_id):
    """Exporta uma sessão para Markdown."""
    from .cold_export import ColdExporter

    db = Database()
    exporter = ColdExporter(db)
    path = exporter.export_session(session_id)
    if path:
        click.echo(f"Exportado: {path}")
    else:
        click.echo(f"Sessão não encontrada: {session_id}")
