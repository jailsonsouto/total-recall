"""
CLI do Vozes da Comunidade.

Comandos:
    vozes batch --input <dir>     Processa corpus offline → popula Warm Store
    vozes query "<texto>"         Gera seção INTELIGÊNCIA DE CONSUMIDOR
    vozes status                  Mostra cobertura do corpus por (categoria, segmento)

Instalação (editable):
    pip install -e .
    # ou
    python -m vozes_da_comunidade.cli batch --input ./data/corpus/

Uso rápido sem instalar:
    python src/cli.py batch --input ./data/corpus/
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import typer

app = typer.Typer(
    name="vozes",
    help="Vozes da Comunidade — inteligência de consumidora para briefings Novex/Embelleze.",
    add_completion=False,
)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ---------------------------------------------------------------------------
# vozes batch
# ---------------------------------------------------------------------------

@app.command()
def batch(
    input_dir: Path = typer.Option(
        ..., "--input", "-i",
        help="Diretório com arquivos .json do corpus TikTok (schema V1).",
        exists=True, file_okay=False, dir_okay=True, readable=True,
    ),
    sample: int = typer.Option(
        0, "--sample", "-n",
        help="Processar apenas os primeiros N comentários (0 = todos).",
    ),
    output_json: Path | None = typer.Option(
        None, "--output", "-o",
        help="Salvar ConsumerIntelligenceOutput em JSON (além do Warm Store).",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """
    Fase offline: processa corpus → extrai triplas → calcula indicadores → persiste.

    Exemplo:
        vozes batch --input ./data/corpus/
        vozes batch --input ./data/corpus/ --sample 50 --verbose
    """
    _setup_logging(verbose)

    from vozes_da_comunidade.batch import BatchPipeline
    from vozes_da_comunidade.indicators import IndicatorCalculator
    from vozes_da_comunidade.memory import post_batch_flush

    typer.echo(f"Iniciando batch em: {input_dir}")

    # Passo 1: extração de triplas
    pipeline = BatchPipeline()
    if sample > 0:
        result = pipeline.run_sample(input_dir, n=sample)
    else:
        result = pipeline.run(input_dir)

    if result.triplets_total == 0:
        typer.echo("Nenhuma tripla extraída. Verifique os arquivos de entrada.", err=True)
        raise typer.Exit(code=1)

    # Passo 2: cálculo de indicadores
    typer.echo("Calculando indicadores PN/AP/Controvérsia...")
    calculator = IndicatorCalculator()
    outputs = calculator.calculate(result.triplets_by_comment)

    typer.echo(f"{len(outputs)} segmentos (categoria × segmento) calculados.")

    # Passo 3: persistência no Warm Store
    typer.echo("Persistindo no Warm Store...")
    flush_result = post_batch_flush(outputs)
    typer.echo(flush_result.summary())

    # Opcional: salvar JSON local
    if output_json:
        serialized = {
            f"{cat}::{seg}": out.to_dict()
            for (cat, seg), out in outputs.items()
        }
        output_json.write_text(
            json.dumps(serialized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        typer.echo(f"JSON salvo em: {output_json}")


# ---------------------------------------------------------------------------
# vozes query
# ---------------------------------------------------------------------------

@app.command()
def query(
    query_text: str = typer.Argument(
        ..., help="Texto de busca (ex: 'máscara de reconstrução cacheadas')."
    ),
    input_dir: Path | None = typer.Option(
        None, "--input", "-i",
        help="Diretório com corpus para processar inline (sem Warm Store).",
        exists=True, file_okay=False, dir_okay=True, readable=True,
    ),
    sample: int = typer.Option(
        50, "--sample", "-n",
        help="N comentários para processar inline (quando --input é fornecido).",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """
    Fase online: gera seção INTELIGÊNCIA DE CONSUMIDOR para um briefing.

    Busca no Warm Store (requer 'vozes batch' anterior) ou processa inline.

    Exemplos:
        vozes query "máscara de reconstrução cacheadas"
        vozes query "cronograma capilar enroladas" --input ./data/corpus/ --sample 100
    """
    _setup_logging(verbose)

    from vozes_da_comunidade.synthesis import synthesize

    direct_outputs = None

    if input_dir:
        # Modo inline: processa uma amostra e usa diretamente
        typer.echo(f"Processando amostra de {sample} comentários em: {input_dir}")
        from vozes_da_comunidade.batch import BatchPipeline
        from vozes_da_comunidade.indicators import IndicatorCalculator

        pipeline = BatchPipeline()
        result = pipeline.run_sample(input_dir, n=sample)

        if result.triplets_total == 0:
            typer.echo("Nenhuma tripla extraída. Tente com --sample maior.", err=True)
            raise typer.Exit(code=1)

        calculator = IndicatorCalculator()
        direct_outputs = calculator.calculate(result.triplets_by_comment)
        typer.echo(f"{len(direct_outputs)} segmentos calculados. Sintetizando...")
    else:
        typer.echo(f"Buscando no Warm Store: \"{query_text}\"")

    synthesis = synthesize(
        query=query_text,
        direct_outputs=direct_outputs,
    )

    typer.echo("\n" + "=" * 70)
    typer.echo(synthesis.section_text)
    typer.echo("=" * 70)

    if verbose:
        typer.echo(
            f"\n[meta] fontes={synthesis.sources_used} | "
            f"modelo={synthesis.model_used} | "
            f"tokens={synthesis.tokens_in}in/{synthesis.tokens_out}out"
        )


# ---------------------------------------------------------------------------
# vozes status
# ---------------------------------------------------------------------------

@app.command()
def status(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """
    Mostra cobertura do corpus no Warm Store por (categoria, segmento).
    """
    _setup_logging(verbose)

    from vozes_da_comunidade import config as cfg

    sys_path = cfg.MEMORIA_VIVA_PATH
    if sys_path and sys_path not in sys.path:
        sys.path.insert(0, sys_path)

    try:
        from memoria_viva.database import Database      # type: ignore
        from memoria_viva.vector_store import SQLiteVectorStore  # type: ignore
        from memoria_viva.embeddings import get_embedding_provider  # type: ignore

        db = Database()
        embed = get_embedding_provider()
        store = SQLiteVectorStore(db, embed)

        with db.connection() as conn:
            rows = conn.execute(
                "SELECT content, metadata FROM chunks WHERE collection = ? ORDER BY created_at DESC",
                ["vozes_comunidade"],
            ).fetchall()

        if not rows:
            typer.echo("Warm Store vazio. Execute 'vozes batch' primeiro.")
            return

        typer.echo(f"\n{'='*60}")
        typer.echo(f"Vozes da Comunidade — Cobertura no Warm Store")
        typer.echo(f"{'='*60}")
        typer.echo(f"Total de registros: {len(rows)}\n")

        for row in rows:
            meta = json.loads(row[1]) if row[1] else {}
            cat = meta.get("categoria", "?")
            seg = meta.get("segmento", "?")
            total = meta.get("total_comentarios", 0)
            score = meta.get("score_oportunidade", 0)
            typer.echo(
                f"  {cat} × {seg}: "
                f"{total} comentários | oportunidade={score}/10"
            )

    except ImportError:
        typer.echo(
            "Memória Viva não disponível. Verificando cache local...", err=True
        )
        cache_dir = Path("data/vozes_cache")
        if cache_dir.exists():
            files = list(cache_dir.glob("*.json"))
            typer.echo(f"Cache local: {len(files)} arquivos em {cache_dir}")
            for f in files:
                typer.echo(f"  {f.stem}")
        else:
            typer.echo("Nenhum dado encontrado. Execute 'vozes batch' primeiro.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
