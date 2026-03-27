"""
cli.py — Interface de linha de comando do Total Recall
"""

import json
import sys
import shutil
from datetime import datetime, timezone
from pathlib import Path

import click

from .config import DATA_DIR, DB_PATH, EXPORTS_PATH, SESSIONS_ROOT
from .database import Database
from .embeddings import get_embedding_provider
from .models import highlight_text


def _score_bar(score: float, width: int = 10) -> str:
    """Barra visual de relevância: ▓▓▓▓▓▓░░░░"""
    filled = max(0, min(width, int(score * width)))
    return "▓" * filled + "░" * (width - filled)


def _age_label(ts: datetime) -> str:
    """Idade legível: 'há 2d', 'há 3h', etc."""
    if not ts:
        return ""
    now = datetime.now(timezone.utc)
    ts_utc = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
    delta = now - ts_utc
    days = delta.days
    if days > 30:
        return f"ha {days // 30}m"
    if days > 0:
        return f"ha {days}d"
    hours = delta.seconds // 3600
    if hours > 0:
        return f"ha {hours}h"
    return "agora"


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
        click.echo(f"  Embedding: ollama / {provider.model_name} ({provider.dimensions()} dims)")
    else:
        click.echo("  Embedding: INDISPONIVEL (FTS5-only mode)")
        from .config import OLLAMA_EMBED_MODEL
        click.echo(f"    Dica: instale Ollama e rode 'ollama pull {OLLAMA_EMBED_MODEL}'")

    # 4. Verifica sessões
    if SESSIONS_ROOT.exists():
        jsonl_count = sum(1 for _ in SESSIONS_ROOT.rglob("*.jsonl"))
        click.echo(f"  Sessões encontradas: {jsonl_count} arquivos JSONL em {SESSIONS_ROOT}")
    else:
        click.echo(f"  Sessões: diretório não encontrado ({SESSIONS_ROOT})")

    # 5. Instala skill (novo formato: ~/.claude/skills/recall/SKILL.md)
    skill_src = Path(__file__).parent.parent.parent / "skill" / "recall.md"
    skill_dst = Path.home() / ".claude" / "skills" / "recall" / "SKILL.md"
    if skill_src.exists():
        skill_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skill_src, skill_dst)
        click.echo(f"  Skill /recall instalada: {skill_dst}")
        # Limpa local antigo se existir
        old_dst = Path.home() / ".claude" / "commands" / "recall.md"
        if old_dst.exists():
            old_dst.unlink()
            click.echo(f"  Removido local antigo: {old_dst}")
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
        click.echo(f"  Embedding: ollama / {provider.model_name} ({provider.dimensions()} dims)")
    else:
        from .config import OLLAMA_EMBED_MODEL, EMBEDDING_DIMENSIONS
        click.echo(f"  Embedding: INDISPONIVEL (modo FTS5-only)")
        click.echo(f"    Esperado: {OLLAMA_EMBED_MODEL} ({EMBEDDING_DIMENSIONS} dims)")

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
@click.option("--output", "-o", default=None,
              help="Salva resultado em arquivo Markdown (clipping)")
def search(query, limit, session, fmt, output):
    """Busca em todas as sessões indexadas."""
    from .recall_engine import RecallEngine
    from .vector_store import SQLiteVectorStore

    db = Database()
    provider = get_embedding_provider()
    vector_store = SQLiteVectorStore(db, provider)
    engine = RecallEngine(db, vector_store)

    ctx = engine.recall(query, limit=limit, session_id=session)

    if fmt == "context":
        content = ctx.format_for_context()
        click.echo(content)
        if output:
            _save_clip(query, content, output)
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
                "sources": r.sources,
            })
        output = {
            "results": results,
            "query_info": ctx.query_info,
        }
        click.echo(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        # rich (default) — com highlighting, fontes e indicadores visuais
        if not ctx.results:
            click.echo(f"Nenhum resultado para: \"{query}\"")
            return

        use_color = sys.stdout.isatty()

        click.echo(f"Resultados para: \"{query}\" ({len(ctx.results)} encontrados)\n")

        # Expansion summary
        expansions = ctx.query_info.get("expansions", [])
        if expansions:
            exp_parts = []
            for exp in expansions:
                label = "fuzzy" if exp["type"] == "fuzzy" else "abrev"
                targets = ", ".join(exp["expanded"][:3])
                exp_parts.append(f"{label}: {exp['original']} → {targets}")
            click.echo(f"  Expansoes: {'; '.join(exp_parts)}\n")

        # Collect highlight terms
        highlight_terms = _collect_highlight_terms(query, ctx.query_info)

        for i, r in enumerate(ctx.results, 1):
            ts = r.timestamp.strftime("%d/%m/%Y %H:%M") if r.timestamp else "?"
            age = _age_label(r.timestamp) if r.timestamp else ""
            sources_str = " + ".join(s.upper() for s in r.sources) if r.sources else "?"
            bar = _score_bar(r.score)

            click.echo(f"  [{i}] {bar} {r.score:.2f} | {r.project_label} — {r.session_title}")
            click.echo(f"      Sessao {r.session_id[:8]} | {ts} ({age}) | {sources_str}")

            # Mostra trecho (primeiros 300 chars) com highlighting
            preview = r.content[:300].replace("\n", " ")
            if len(r.content) > 300:
                preview += "..."
            if use_color and highlight_terms:
                preview = highlight_text(preview, highlight_terms, mode="ansi")
            click.echo(f"      {preview}")
            click.echo()

        if output:
            clip_md = ctx.format_for_context()
            _save_clip(query, clip_md, output)


def _save_clip(query: str, content: str, output: str):
    """Salva resultado de busca como clipping Markdown."""
    import re
    clips_dir = Path.home() / ".total-recall" / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    if output == "-auto-":
        slug = re.sub(r"[^\w\s-]", "", query.lower())
        slug = re.sub(r"[\s]+", "-", slug)[:40].strip("-")
        date = datetime.now().strftime("%Y-%m-%d")
        path = clips_dir / f"{date}_{slug}.md"
    else:
        path = Path(output)
        if not path.is_absolute():
            path = clips_dir / path

    header = (
        f"# Clipping — {query}\n\n"
        f"*Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} "
        f"via `total-recall search`*\n\n---\n\n"
    )
    path.write_text(header + content, encoding="utf-8")
    click.echo(f"\n  Clipping salvo: {path}", err=True)


def _collect_highlight_terms(query: str, query_info: dict) -> list[str]:
    """Coleta termos para highlighting a partir da query e expansões."""
    terms = set()
    for word in query.lower().split():
        clean = word.strip(".,!?;:")
        if clean and len(clean) >= 2:
            terms.add(clean)
    for exp in query_info.get("expansions", []):
        for expanded in exp["expanded"]:
            terms.add(expanded.lower())
    return sorted(terms, key=len, reverse=True)


@main.command()
def doctor():
    """Diagnóstico detalhado do sistema — provider, índice, skill."""
    from .config import (
        EMBED_PROVIDER, OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL,
        EMBEDDING_DIMENSIONS, OPENAI_API_KEY, OPENAI_EMBED_MODEL,
    )

    ok = True

    def check(label, status, detail=""):
        nonlocal ok
        icon = "OK" if status else "!!"
        if not status:
            ok = False
        line = f"  [{icon}] {label}"
        if detail:
            line += f": {detail}"
        click.echo(line)

    click.echo("Total Recall — Doctor\n")

    # ── 1. Banco de dados ──────────────────────────────────────────
    click.echo("Banco de dados")
    if not DB_PATH.exists():
        check("Banco", False, f"não encontrado em {DB_PATH} — rode 'total-recall init'")
        click.echo()
    else:
        size_mb = DB_PATH.stat().st_size / (1024 * 1024)
        check("Banco", True, f"{DB_PATH} ({size_mb:.2f} MB)")

        db = Database()
        with db.connection() as conn:
            sessions_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            chunks_total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            chunks_with_emb = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE has_embedding = TRUE"
            ).fetchone()[0]
            chunks_without_emb = chunks_total - chunks_with_emb

            check("Sessões indexadas", True, str(sessions_count))
            check("Chunks totais", True, str(chunks_total))

            if chunks_without_emb > 0:
                pct = chunks_without_emb / chunks_total * 100 if chunks_total else 0
                check(
                    "Chunks sem embedding", False,
                    f"{chunks_without_emb} ({pct:.0f}%) — "
                    f"rode 'total-recall index' com Ollama ativo para completar"
                )
            else:
                check("Chunks sem embedding", True, "0 — todos têm embedding")

            # Dimensão real no índice vetorial
            vec_dim = None
            try:
                row = conn.execute(
                    "SELECT embedding FROM chunks_vec LIMIT 1"
                ).fetchone()
                if row and row[0]:
                    vec_dim = len(row[0]) // 4  # 4 bytes por float32
            except Exception:
                pass

            if vec_dim:
                dim_ok = vec_dim == EMBEDDING_DIMENSIONS
                check(
                    "Dimensão no índice", dim_ok,
                    f"{vec_dim} dims"
                    + (f" (config espera {EMBEDDING_DIMENSIONS})" if not dim_ok else "")
                )
            else:
                check("Dimensão no índice", True, "índice vazio ou sem vetores")

            # Última indexação
            last_run = conn.execute(
                "SELECT started_at, files_indexed, chunks_created "
                "FROM indexing_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if last_run:
                check(
                    "Última indexação", True,
                    f"{last_run['started_at']} "
                    f"({last_run['files_indexed']} arquivos, "
                    f"{last_run['chunks_created']} chunks)"
                )
            else:
                check("Última indexação", False, "nenhuma — rode 'total-recall index'")

        click.echo()

    # ── 2. Provider de embedding ───────────────────────────────────
    click.echo("Embedding")
    check("Provider configurado", True, EMBED_PROVIDER)

    if EMBED_PROVIDER == "ollama":
        # Testa Ollama em etapas para dar diagnóstico preciso
        try:
            import ollama as _ollama
            models_resp = _ollama.list()
            installed = [m.model for m in models_resp.models]
            check("Ollama acessível", True, OLLAMA_BASE_URL)

            model_found = any(
                OLLAMA_EMBED_MODEL in m or m in OLLAMA_EMBED_MODEL
                for m in installed
            )
            if model_found:
                check("Modelo instalado", True, OLLAMA_EMBED_MODEL)
                # Testa embedding real
                try:
                    resp = _ollama.embed(model=OLLAMA_EMBED_MODEL, input="test")
                    actual_dim = len(resp["embeddings"][0])
                    config_dim = EMBEDDING_DIMENSIONS
                    dim_ok = actual_dim >= config_dim
                    if actual_dim > config_dim:
                        check(
                            "Dimensão do modelo", True,
                            f"{actual_dim} dims (truncado para {config_dim} pela config)"
                        )
                    elif actual_dim == config_dim:
                        check("Dimensão do modelo", True, f"{actual_dim} dims")
                    else:
                        check(
                            "Dimensão do modelo", False,
                            f"modelo retorna {actual_dim} dims, "
                            f"config espera {config_dim} — ajuste TOTAL_RECALL_EMBEDDING_DIMENSIONS"
                        )
                    check("Embedding funcional", True, "modo híbrido ativo")
                except Exception as e:
                    check("Embedding funcional", False, str(e))
            else:
                check(
                    "Modelo instalado", False,
                    f"{OLLAMA_EMBED_MODEL} não encontrado — "
                    f"rode 'ollama pull {OLLAMA_EMBED_MODEL}'"
                )
                check("Embedding funcional", False, "modelo ausente — modo FTS5-only")

        except Exception as e:
            err = str(e)
            if "connection" in err.lower() or "connect" in err.lower():
                check("Ollama acessível", False,
                      f"não está rodando em {OLLAMA_BASE_URL} — inicie o Ollama")
            else:
                check("Ollama acessível", False, err)
            check("Embedding funcional", False, "Ollama indisponível — modo FTS5-only")

    elif EMBED_PROVIDER == "openai":
        if OPENAI_API_KEY:
            check("OPENAI_API_KEY", True, "configurada")
        else:
            check("OPENAI_API_KEY", False, "não definida — defina a variável de ambiente")

        actual_openai_dims = 1536
        if actual_openai_dims != EMBEDDING_DIMENSIONS:
            check(
                "Dimensão OpenAI vs config", False,
                f"OpenAI retorna {actual_openai_dims} dims, "
                f"config tem {EMBEDDING_DIMENSIONS} — "
                f"defina TOTAL_RECALL_EMBEDDING_DIMENSIONS=1536 e reindexe com --full"
            )
        else:
            check("Dimensão", True, f"{actual_openai_dims} dims")

        click.echo(
            "  [!!] AVISO: OpenAIEmbedProvider não usa instruction-aware embedding.\n"
            "       Qualidade de recuperação é inferior ao Ollama para este corpus.\n"
            "       Considere passar 'dimensions' e 'input_type' na chamada à API."
        )

    click.echo()

    # ── 3. Skill /recall ───────────────────────────────────────────
    click.echo("Skill /recall")
    skill_path = Path.home() / ".claude" / "skills" / "recall" / "SKILL.md"
    skill_ok = skill_path.exists()
    check("Instalada", skill_ok,
          str(skill_path) if skill_ok else f"não encontrada — rode 'total-recall init'")

    old_path = Path.home() / ".claude" / "commands" / "recall.md"
    if old_path.exists():
        check("Local antigo", False,
              f"arquivo legado em {old_path} — pode conflitar, remova manualmente")

    click.echo()

    # ── 4. Sessões disponíveis ─────────────────────────────────────
    click.echo("Sessões")
    if SESSIONS_ROOT.exists():
        jsonl_files = list(SESSIONS_ROOT.rglob("*.jsonl"))
        subagent_count = sum(1 for f in jsonl_files if "subagent" in str(f))
        main_count = len(jsonl_files) - subagent_count
        check("Diretório", True, str(SESSIONS_ROOT))
        check("Arquivos JSONL", True, f"{main_count} sessões, {subagent_count} subagentes")
    else:
        check("Diretório de sessões", False,
              f"{SESSIONS_ROOT} não existe — verifique TOTAL_RECALL_SESSIONS")

    click.echo()
    if ok:
        click.echo("Sistema saudável.")
    else:
        click.echo("Há itens que precisam de atenção (marcados com !!).")


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
