"""Command line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from litsearch.config import get_settings
from litsearch.connectors.registry import list_sources
from litsearch.db.session import init_database, sqlite_path_from_url
from litsearch.exceptions import LitSearchValidationError
from litsearch.log_utils import configure_logging
from litsearch.services.search_service import SearchService

app = typer.Typer(help="Literature search CLI.")
config_app = typer.Typer(help="Inspect configuration.")
db_app = typer.Typer(help="Database commands.")
console = Console()


@app.command()
def sources() -> None:
    """Show built-in source status."""

    settings = get_settings()
    configure_logging(settings)
    table = Table("source id", "display name", "capabilities", "requires", "configured")
    for source in list_sources(settings):
        table.add_row(
            source.id,
            source.display_name,
            ", ".join(source.capabilities),
            ", ".join(source.requires),
            str(source.configured).lower(),
        )
    console.print(table)


@app.command()
def search(
    query: str,
    sources: Annotated[
        str,
        typer.Option(help="Comma-separated search sources: openalex,crossref,ieee,scopus,wos."),
    ] = "openalex,crossref",
    limit: Annotated[int, typer.Option(help="Maximum results per source.")] = 10,
    no_enrich: Annotated[
        bool,
        typer.Option("--no-enrich", help="Disable Unpaywall DOI enrich."),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output structured JSON.")] = False,
) -> None:
    """Search metadata sources and save results."""

    settings = get_settings()
    configure_logging(settings)
    source_ids = [source.strip().lower() for source in sources.split(",") if source.strip()]
    try:
        summary = SearchService(settings).search(
            query=query,
            sources=source_ids,
            limit=limit,
            enrich_unpaywall=not no_enrich,
        )
    except LitSearchValidationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    if json_output:
        typer.echo(summary.model_dump_json(indent=2))
        return

    table = Table("title", "year", "doi", "source", "open_access")
    for paper in summary.papers:
        table.add_row(
            paper.title,
            str(paper.publication_year or ""),
            paper.doi or "",
            paper.source,
            "" if paper.is_open_access is None else str(paper.is_open_access).lower(),
        )
    console.print(table)
    console.print(f"search_run_id: {summary.search_run_id}")
    console.print(f"total_raw: {summary.total_raw}")
    console.print(f"total_saved: {summary.total_saved}")
    console.print(f"errors: {summary.errors or {}}")


@config_app.command("show")
def config_show() -> None:
    """Show sanitized configuration."""

    settings = get_settings()
    configure_logging(settings)
    typer.echo(json.dumps(settings.safe_dump(), indent=2, sort_keys=True))


@db_app.command("init")
def db_init() -> None:
    """Initialize the configured database through Alembic."""

    settings = get_settings()
    configure_logging(settings)
    revision = init_database(settings)
    db_path = sqlite_path_from_url(settings.db_url)
    display_path = str(db_path or Path(settings.db_url))
    typer.echo(f"Database: {display_path}")
    typer.echo(f"Revision: {revision}")


app.add_typer(config_app, name="config")
app.add_typer(db_app, name="db")
