"""
cli.py — Interface de linha de comando da Memória Viva
======================================================

Este arquivo define os comandos que Jay (ou qualquer PM) pode
rodar no terminal para interagir com a memória do sistema.

COMANDOS DISPONÍVEIS:

    memoria-viva init
        Inicializa o banco de dados e o Cold Store.
        Rodar UMA VEZ após a instalação.

    memoria-viva status
        Mostra o estado atual da memória:
        quantos briefings, vetores, calibrações, etc.

    memoria-viva search "sérum de transição"
        Busca na memória (vetorial + keyword).
        Mostra padrões similares encontrados.

    memoria-viva briefings
        Lista todos os briefings registrados com status.

    memoria-viva flush <thread_id> GO -r "ativo validado" -r "preço ok"
        Executa o Committee Flush manualmente.
        Normalmente disparado pelo polling do Basecamp (ADR-006).

    memoria-viva bvs-real <thread_id> 85.0
        Insere o BVS Real de um briefing.
        Chamado quando os dados de sell-through Onda 1 chegam.

INSTALAÇÃO:
    pip install -e .
    (isso torna o comando "memoria-viva" disponível no terminal)
"""

import json

import click

from .memory_manager import MemoryManager


@click.group()
def main():
    """Memória Viva — Agente 8 (Memory Manager) CLI"""
    pass


@main.command()
def init():
    """Inicializa o banco de dados e a estrutura do Cold Store."""
    click.echo("\nInicializando Memória Viva...\n")

    # Cria banco + tabelas
    mm = MemoryManager()
    click.echo(f"  Banco de dados: {mm.db.db_path}")
    click.echo(f"  Cold Store:     {mm.cold_store.base_path}")

    # Verifica embedding provider
    try:
        test_vector = mm.embed.embed("teste de conexão")
        click.echo(
            f"  Embedding:      {mm.embed.model_name} "
            f"({mm.embed.dimensions()} dims) — OK"
        )
    except Exception as e:
        click.echo(f"  Embedding:      ERRO — {e}")
        click.echo("")
        click.echo("  Para resolver:")
        click.echo("    1. Verifique se o Ollama está rodando: ollama serve")
        click.echo("    2. Verifique se o modelo está baixado: ollama pull nomic-embed-text")
        click.echo("    3. Ou mude para OpenAI no .env: EMBED_PROVIDER=openai")
        return

    click.echo("\nMemória Viva inicializada com sucesso!")
    click.echo("Próximo passo: edite cold_store/BRAND_MEMORY.md com o Código Genético da marca.\n")


@main.command()
def status():
    """Mostra o estado atual da memória."""
    mm = MemoryManager()
    info = mm.get_status()

    click.echo("\n══ Memória Viva — Status ══\n")
    click.echo(f"  Briefings processados:    {info['briefings_total']}")
    click.echo(f"  Aguardando Comitê:        {info['briefings_pendentes_comite']}")
    click.echo(f"  Padrões ativos:           {info['padroes_ativos']}")
    click.echo(f"  Vetores no Warm Store:    {info['vetores_no_warm_store']}")
    click.echo(f"  Calibrações realizadas:   {info['calibracoes_realizadas']}")
    click.echo(
        f"  Embedding:                {info['embedding_provider']} "
        f"({info['embedding_dimensions']} dims)"
    )

    if info["ultima_calibracao"]:
        cal = info["ultima_calibracao"]
        click.echo(f"\n  Última calibração BVS:")
        click.echo(f"    Ajuste:    {cal['ajuste_bvs']:+.2f}")
        click.echo(f"    Confiança: {cal['confianca']}")
        click.echo(f"    Dados:     {cal['pontos_de_dados']} briefings")

    click.echo()


@main.command()
@click.argument("query")
@click.option(
    "--collection", "-c", default=None,
    help="Filtrar por coleção (briefing_patterns, segment_insights, etc.)",
)
@click.option("--limit", "-n", default=5, help="Número de resultados")
def search(query, collection, limit):
    """Busca na memória (vetorial + keyword)."""
    mm = MemoryManager()

    click.echo(f'\nBuscando: "{query}"\n')
    results = mm.vector_store.hybrid_search(query, collection, limit)

    if not results:
        click.echo("  Nenhum resultado encontrado.")
        click.echo("  (a memória está vazia — registre briefings primeiro)")
    else:
        for i, r in enumerate(results, 1):
            click.echo(f"  {i}. [{r.collection}] (distância: {r.distance:.4f})")
            # Mostra até 150 caracteres do conteúdo
            preview = r.content[:150] + ("..." if len(r.content) > 150 else "")
            click.echo(f"     {preview}")
            if r.metadata:
                click.echo(
                    f"     metadata: {json.dumps(r.metadata, ensure_ascii=False)}"
                )
            click.echo()


@main.command()
def briefings():
    """Lista todos os briefings registrados."""
    mm = MemoryManager()

    with mm.db.connection() as conn:
        rows = conn.execute("""
            SELECT thread_id, product_idea, segment, current_status,
                   bvs_preditivo, bvs_real, committee_decision, created_at
            FROM briefing_threads
            ORDER BY created_at DESC
        """).fetchall()

    if not rows:
        click.echo("\nNenhum briefing registrado ainda.\n")
        return

    click.echo(f"\n══ Briefings ({len(rows)} total) ══\n")
    for row in rows:
        # Ícone visual do status
        status_icon = {
            "running": "[...]",
            "pending_committee": "[>>>]",
            "committee_go": "[ GO]",
            "committee_no_go": "[NO!]",
            "archived": "[ARQ]",
        }.get(row["current_status"], "[???]")

        bvs_pred = f"BVS pred:{row['bvs_preditivo']:.1f}" if row["bvs_preditivo"] else "BVS pred:—"
        bvs_real = f"real:{row['bvs_real']:.1f}" if row["bvs_real"] else "real:—"

        click.echo(f"  {status_icon} {row['product_idea']}")
        click.echo(
            f"         ID: {row['thread_id'][:12]}...  "
            f"Seg: {row['segment'] or '—'}  "
            f"{bvs_pred} {bvs_real}"
        )
        click.echo()


@main.command("bvs-real")
@click.argument("thread_id")
@click.argument("sell_through", type=float)
def bvs_real(thread_id, sell_through):
    """
    Insere o BVS Real de um briefing (ADR-007).

    THREAD_ID: UUID do briefing (use 'memoria-viva briefings' para ver)
    SELL_THROUGH: percentual de sell-through Onda 1 (ex: 85.0 = 85%)
    """
    mm = MemoryManager()

    try:
        result = mm.insert_bvs_real(thread_id, sell_through)
        deviation = result["bvs_preditivo"] - result["bvs_real"]
        click.echo(f"\nBVS Real inserido com sucesso:\n")
        click.echo(f"  Produto:       {result['product_idea']}")
        click.echo(f"  Sell-through:  {result['sell_through_pct']:.1f}%")
        click.echo(f"  BVS Preditivo: {result['bvs_preditivo']:.2f}")
        click.echo(f"  BVS Real:      {result['bvs_real']}")
        click.echo(f"  Desvio:        {deviation:+.2f}")
        click.echo()
    except ValueError as e:
        click.echo(f"\nErro: {e}\n")


@main.command()
@click.argument("thread_id")
@click.argument("decision", type=click.Choice(["GO", "NO-GO", "HOLD"]))
@click.option(
    "--reasons", "-r", multiple=True, required=True,
    help="Motivo da decisão (pode repetir: -r 'motivo1' -r 'motivo2')",
)
@click.option("--notes", "-n", default="", help="Observações adicionais")
def flush(thread_id, decision, reasons, notes):
    """
    Executa o Committee Flush manualmente.

    THREAD_ID: UUID do briefing
    DECISION: GO, NO-GO ou HOLD

    Exemplo:
        memoria-viva flush abc-123 GO -r "ativo validado" -r "preço ok"
    """
    mm = MemoryManager()

    try:
        mm.committee_flush(thread_id, decision, list(reasons), notes)
        click.echo(f"\nCommittee Flush executado com sucesso!\n")
        click.echo(f"  Briefing: {thread_id}")
        click.echo(f"  Decisão:  {decision}")
        click.echo(f"  Motivos:  {', '.join(reasons)}")
        if notes:
            click.echo(f"  Notas:    {notes}")
        click.echo()
    except ValueError as e:
        click.echo(f"\nErro: {e}\n")


@main.command("memory-read")
@click.argument("product_idea")
def memory_read(product_idea):
    """
    Mostra o contexto que seria injetado para uma ideia de produto.

    Útil para testar: mostra o que os agentes "veriam" antes de
    processar esta ideia.

    Exemplo:
        memoria-viva memory-read "sérum de transição com quinoa"
    """
    mm = MemoryManager()

    click.echo(f'\nMemory Read para: "{product_idea}"\n')
    ctx = mm.memory_read(product_idea)

    click.echo(f"  Tokens estimados: {ctx.total_tokens_estimate}")
    click.echo(f"  Padrões históricos: {len(ctx.historical_patterns)}")
    click.echo(f"  Alertas de rejeição: {len(ctx.rejection_alerts)}")
    click.echo(f"  Calibrações: {'sim' if ctx.score_calibrations else 'não'}")
    click.echo(f"  Insights de segmento: {len(ctx.segment_insights)}")

    if ctx.rejection_alerts:
        click.echo("\n  ALERTAS:")
        for alert in ctx.rejection_alerts:
            click.echo(f"    {alert}")

    click.echo("\n── Contexto formatado ──\n")
    formatted = ctx.format_for_injection()
    if formatted:
        click.echo(formatted)
    else:
        click.echo("  (memória vazia — nenhum contexto para injetar)")

    click.echo()
