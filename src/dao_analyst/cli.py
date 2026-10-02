"""Command-line entry point: ``dao-analyst <command>``."""

from __future__ import annotations

import json

import typer

from dao_analyst.config import load_dao_config
from dao_analyst.data.fetch import FetchMode
from dao_analyst.data.ingest import run_ingest
from dao_analyst.logging_setup import configure_logging
from dao_analyst.settings import get_settings

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def main(log_level: str = typer.Option("INFO", help="Log level")) -> None:
    configure_logging(log_level, json=False)


@app.command()
def ingest(mode: FetchMode = FetchMode.REPLAY) -> None:
    """Fetch (or replay) treasury activity and build the local DuckDB store.

    --mode replay rebuilds from committed fixtures (offline); --mode record calls the APIs
    and saves fixtures.
    """
    settings = get_settings()
    cfg = load_dao_config(settings.dao_config)
    result = run_ingest(cfg, settings, mode)
    typer.echo(
        f"Snapshot: blocks {result.snapshot.start_block}..{result.snapshot.end_block} "
        f"(end {result.snapshot.end_timestamp})"
    )
    typer.echo(f"Transfers stored: {result.transfers}")
    typer.echo(
        "Normalization: " + json.dumps({k: v for k, v in result.report.items() if k != "notes"})
    )
    for check in result.balance_checks:
        typer.echo("Balance check: " + json.dumps(check))


@app.command()
def ask(
    question: str,
    provider: str | None = typer.Option(None, help="LLM provider (default from settings)"),
    model: str | None = typer.Option(None, help="Model id (default from settings)"),
    show_trace: bool = typer.Option(False, help="Print tool calls and verification"),
) -> None:
    """Ask the treasury agent a question (needs a built store: run `ingest` first)."""
    from dao_analyst.agent.factory import build_agent, build_llm

    settings = get_settings()
    cfg = load_dao_config(settings.dao_config)
    agent = build_agent(cfg, settings, build_llm(settings, provider=provider, model=model))
    result = agent.answer(question)
    typer.echo(result.text)
    if show_trace:
        typer.echo("\n--- trace ---")
        for call in result.tool_calls:
            typer.echo(json.dumps(call))
        for v in result.verification:
            typer.echo("verification: " + json.dumps(v))
        typer.echo(
            f"outcome={result.outcome.value} llm_calls={result.llm_calls} "
            f"tokens={result.input_tokens}+{result.output_tokens} "
            f"latency={result.latency_s:.1f}s"
        )


if __name__ == "__main__":
    app()
