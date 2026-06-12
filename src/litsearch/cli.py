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
from litsearch.models import LibraryStatus
from litsearch.services.export_service import ExportFilters, ExportService
from litsearch.services.library_service import LibraryService
from litsearch.services.query_service import PaperFilters, QueryService
from litsearch.services.search_service import SearchService

app = typer.Typer(help="Literature search CLI.")
config_app = typer.Typer(help="Inspect configuration.")
db_app = typer.Typer(help="Database commands.")
searches_app = typer.Typer(help="Search history commands.")
papers_app = typer.Typer(help="Paper library commands.")
library_app = typer.Typer(help="Library item commands.")
tags_app = typer.Typer(help="Tag commands.")
console = Console()


def _settings():
    settings = get_settings()
    configure_logging(settings)
    return settings


def _echo_json(value: object) -> None:
    if hasattr(value, "model_dump_json"):
        typer.echo(value.model_dump_json(indent=2))
        return
    typer.echo(json.dumps(value, indent=2, ensure_ascii=False))


def _parse_paper_ids(value: str | None) -> list[int] | None:
    if not value:
        return None
    try:
        return [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise LitSearchValidationError("paper ids must be comma-separated integers") from exc


def _run_or_exit(func):
    try:
        return func()
    except LitSearchValidationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@app.command()
def sources() -> None:
    """Show built-in source status."""

    settings = _settings()
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
    year_from: Annotated[
        int | None,
        typer.Option(help="Keep results from this year onward."),
    ] = None,
    year_to: Annotated[int | None, typer.Option(help="Keep results up to this year.")] = None,
    open_access_only: Annotated[
        bool,
        typer.Option("--open-access-only", help="Save only open-access results."),
    ] = False,
) -> None:
    """Search metadata sources and save results."""

    settings = _settings()
    source_ids = [source.strip().lower() for source in sources.split(",") if source.strip()]
    summary = _run_or_exit(
        lambda: SearchService(settings).search(
            query=query,
            sources=source_ids,
            limit=limit,
            enrich_unpaywall=not no_enrich,
            year_from=year_from,
            year_to=year_to,
            open_access_only=open_access_only,
        )
    )

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

    settings = _settings()
    typer.echo(json.dumps(settings.safe_dump(), indent=2, sort_keys=True))


@db_app.command("init")
def db_init() -> None:
    """Initialize the configured database through Alembic."""

    settings = _settings()
    revision = init_database(settings)
    db_path = sqlite_path_from_url(settings.db_url)
    display_path = str(db_path or Path(settings.db_url))
    typer.echo(f"Database: {display_path}")
    typer.echo(f"Revision: {revision}")


@searches_app.command("list")
def searches_list(
    limit: Annotated[int, typer.Option(help="Maximum search runs to show.")] = 20,
    json_output: Annotated[bool, typer.Option("--json", help="Output structured JSON.")] = False,
) -> None:
    """List search history."""

    runs = QueryService(_settings()).list_search_runs(limit)
    if json_output:
        _echo_json([run.model_dump() for run in runs])
        return
    table = Table(
        "id",
        "query",
        "sources",
        "status",
        "started_at",
        "finished_at",
        "results",
        "errors",
    )
    for run in runs:
        table.add_row(
            str(run.id),
            run.query,
            ",".join(run.sources),
            run.status,
            run.started_at or "",
            run.finished_at or "",
            str(run.result_count),
            json.dumps(run.errors, ensure_ascii=False) if run.errors else "",
        )
    console.print(table)


@searches_app.command("get")
def searches_get(
    search_run_id: int,
    json_output: Annotated[bool, typer.Option("--json", help="Output structured JSON.")] = False,
) -> None:
    """Show one search run and its papers."""

    detail = QueryService(_settings()).get_search_run(search_run_id)
    if not detail:
        typer.echo(f"Search run not found: {search_run_id}", err=True)
        raise typer.Exit(1)
    if json_output:
        _echo_json(detail)
        return
    console.print(f"search_run_id: {detail.id}")
    console.print(f"query: {detail.query}")
    console.print(f"sources: {', '.join(detail.sources)}")
    console.print(f"status: {detail.status}")
    table = Table("id", "title", "year", "doi", "sources", "status", "favorite", "tags")
    for paper in detail.papers:
        table.add_row(
            str(paper.id),
            paper.title,
            str(paper.year or ""),
            paper.doi or "",
            ",".join(paper.sources),
            paper.status,
            str(paper.favorite).lower(),
            ",".join(paper.tags),
        )
    console.print(table)


@papers_app.command("list")
def papers_list(
    query: Annotated[str | None, typer.Option(help="Filter title, abstract, or DOI.")] = None,
    source: Annotated[str | None, typer.Option(help="Filter by source id.")] = None,
    year_from: Annotated[int | None, typer.Option(help="Filter from year.")] = None,
    year_to: Annotated[int | None, typer.Option(help="Filter to year.")] = None,
    tag: Annotated[str | None, typer.Option(help="Filter by tag.")] = None,
    status: Annotated[LibraryStatus | None, typer.Option(help="Filter by library status.")] = None,
    favorite: Annotated[bool, typer.Option("--favorite", help="Show favorites only.")] = False,
    limit: Annotated[int, typer.Option(help="Maximum papers to show.")] = 50,
    json_output: Annotated[bool, typer.Option("--json", help="Output structured JSON.")] = False,
) -> None:
    """List papers in the local database."""

    papers = QueryService(_settings()).list_papers(
        PaperFilters(
            query=query,
            source=source,
            year_from=year_from,
            year_to=year_to,
            tag=tag,
            status=status,
            favorite=favorite,
            limit=limit,
        )
    )
    if json_output:
        _echo_json([paper.model_dump() for paper in papers])
        return
    table = Table("id", "title", "year", "doi", "venue", "sources", "status", "favorite", "tags")
    for paper in papers:
        table.add_row(
            str(paper.id),
            paper.title,
            str(paper.year or ""),
            paper.doi or "",
            paper.venue or "",
            ",".join(paper.sources),
            paper.status,
            str(paper.favorite).lower(),
            ",".join(paper.tags),
        )
    console.print(table)


@papers_app.command("get")
def papers_get(
    paper_id: int,
    json_output: Annotated[bool, typer.Option("--json", help="Output structured JSON.")] = False,
) -> None:
    """Show one paper."""

    paper = QueryService(_settings()).get_paper(paper_id)
    if not paper:
        typer.echo(f"Paper not found: {paper_id}", err=True)
        raise typer.Exit(1)
    if json_output:
        _echo_json(paper)
        return
    for key, value in paper.model_dump().items():
        console.print(f"{key}: {value}")


@papers_app.command("tag")
def papers_tag(paper_id: int, tag_name: str) -> None:
    """Add a tag to a paper."""

    tag = _run_or_exit(lambda: LibraryService(_settings()).tag_paper(paper_id, tag_name))
    typer.echo(f"Tagged paper {paper_id} with {tag.name}")


@papers_app.command("untag")
def papers_untag(paper_id: int, tag_name: str) -> None:
    """Remove a tag from a paper."""

    removed = _run_or_exit(lambda: LibraryService(_settings()).untag_paper(paper_id, tag_name))
    typer.echo("Tag removed" if removed else "Tag was not assigned")


@library_app.command("add")
def library_add(
    paper_id: int,
    status: Annotated[LibraryStatus, typer.Option(help="Library status.")] = LibraryStatus.unread,
    favorite: Annotated[
        bool,
        typer.Option("--favorite/--no-favorite", help="Mark as favorite."),
    ] = False,
    rating: Annotated[int | None, typer.Option(help="Rating from 1 to 5.")] = None,
    notes: Annotated[str | None, typer.Option(help="Notes.")] = None,
) -> None:
    """Add or replace library state for a paper."""

    item = _run_or_exit(
        lambda: LibraryService(_settings()).add_or_update_library_item(
            paper_id=paper_id,
            status=status,
            favorite=favorite,
            rating=rating,
            notes=notes,
        )
    )
    _echo_json(item)


@library_app.command("update")
def library_update(
    paper_id: int,
    status: Annotated[LibraryStatus | None, typer.Option(help="Library status.")] = None,
    favorite: Annotated[
        bool | None,
        typer.Option("--favorite/--no-favorite", help="Mark as favorite."),
    ] = None,
    rating: Annotated[int | None, typer.Option(help="Rating from 1 to 5.")] = None,
    notes: Annotated[str | None, typer.Option(help="Notes.")] = None,
) -> None:
    """Update only passed library fields for a paper."""

    item = _run_or_exit(
        lambda: LibraryService(_settings()).update_library_item(
            paper_id=paper_id,
            status=status,
            favorite=favorite,
            rating=rating,
            notes=notes,
            rating_set=rating is not None,
            notes_set=notes is not None,
        )
    )
    _echo_json(item)


@library_app.command("remove")
def library_remove(paper_id: int) -> None:
    """Remove library state without deleting the paper."""

    removed = _run_or_exit(lambda: LibraryService(_settings()).remove_library_item(paper_id))
    typer.echo("Library item removed" if removed else "Library item did not exist")


@tags_app.command("list")
def tags_list(
    json_output: Annotated[bool, typer.Option("--json", help="Output structured JSON.")] = False,
) -> None:
    """List tags."""

    tags = LibraryService(_settings()).list_tags()
    if json_output:
        _echo_json([tag.model_dump() for tag in tags])
        return
    table = Table("id", "name", "papers")
    for tag in tags:
        table.add_row(str(tag.id), tag.name, str(tag.paper_count))
    console.print(table)


@tags_app.command("add")
def tags_add(tag_name: str) -> None:
    """Create a tag."""

    tag = _run_or_exit(lambda: LibraryService(_settings()).add_tag(tag_name))
    _echo_json(tag)


@tags_app.command("remove")
def tags_remove(tag_name: str) -> None:
    """Delete a tag and tag assignments."""

    removed = _run_or_exit(lambda: LibraryService(_settings()).remove_tag(tag_name))
    typer.echo("Tag removed" if removed else "Tag did not exist")


@app.command("export")
def export_cmd(
    format: Annotated[str, typer.Option("--format", help="bibtex, ris, or csv.")],
    output: Annotated[Path, typer.Option("--output", help="Output file path.")],
    paper_ids: Annotated[
        str | None,
        typer.Option("--paper-ids", help="Comma-separated paper ids."),
    ] = None,
    search_run_id: Annotated[
        int | None,
        typer.Option("--search-run-id", help="Search run id."),
    ] = None,
    tag: Annotated[str | None, typer.Option(help="Filter by tag.")] = None,
    favorite: Annotated[bool, typer.Option("--favorite", help="Export favorites only.")] = False,
    status: Annotated[LibraryStatus | None, typer.Option(help="Filter by library status.")] = None,
) -> None:
    """Export papers."""

    summary = _run_or_exit(
        lambda: ExportService(_settings()).export_papers(
            format=format,
            output=output,
            filters=ExportFilters(
                paper_ids=_parse_paper_ids(paper_ids),
                search_run_id=search_run_id,
                tag=tag,
                favorite=favorite,
                status=status,
            ),
        )
    )
    typer.echo(f"Exported {summary.paper_count} papers to {summary.output_path}")


app.add_typer(config_app, name="config")
app.add_typer(db_app, name="db")
app.add_typer(searches_app, name="searches")
app.add_typer(papers_app, name="papers")
app.add_typer(library_app, name="library")
app.add_typer(tags_app, name="tags")
