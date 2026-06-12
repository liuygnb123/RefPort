"""Export papers to BibTeX, RIS, or CSV."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from pydantic import BaseModel
from sqlmodel import Session, select

from litsearch.config import Settings
from litsearch.db.session import create_db_engine, init_database
from litsearch.exceptions import LitSearchValidationError
from litsearch.models import (
    LibraryItem,
    LibraryStatus,
    Paper,
    PaperAuthor,
    PaperSource,
    SearchResultItem,
    Tag,
)
from litsearch.models.library import PaperTag
from litsearch.services.query_service import PaperFilters, QueryService


class ExportFilters(BaseModel):
    paper_ids: list[int] | None = None
    search_run_id: int | None = None
    tag: str | None = None
    favorite: bool = False
    status: LibraryStatus | None = None


class ExportSummary(BaseModel):
    output_path: Path
    format: str
    paper_count: int


class ExportService:
    FORMATS = {"bibtex", "ris", "csv"}

    def __init__(self, settings: Settings):
        self.settings = settings

    def export_papers(self, format: str, output: Path, filters: ExportFilters) -> ExportSummary:
        export_format = format.lower()
        if export_format not in self.FORMATS:
            raise LitSearchValidationError("format must be one of: bibtex, ris, csv")

        init_database(self.settings)
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            papers = self._select_papers(session, filters)
            output.parent.mkdir(parents=True, exist_ok=True)
            if export_format == "csv":
                self._write_csv(session, output, papers)
            elif export_format == "ris":
                output.write_text(self._render_ris(session, papers), encoding="utf-8")
            else:
                output.write_text(self._render_bibtex(session, papers), encoding="utf-8")
            return ExportSummary(
                output_path=output,
                format=export_format,
                paper_count=len(papers),
            )

    def _select_papers(self, session: Session, filters: ExportFilters) -> list[Paper]:
        if filters.paper_ids:
            papers = []
            for paper_id in filters.paper_ids:
                paper = session.get(Paper, paper_id)
                if paper:
                    papers.append(paper)
            return papers
        if filters.search_run_id:
            items = session.exec(
                select(SearchResultItem)
                .where(SearchResultItem.search_run_id == filters.search_run_id)
                .order_by(SearchResultItem.rank)
            ).all()
            seen: set[int] = set()
            papers = []
            for item in items:
                if item.paper_id in seen:
                    continue
                paper = session.get(Paper, item.paper_id)
                if paper:
                    papers.append(paper)
                    seen.add(item.paper_id)
            return papers

        query_filters = PaperFilters(
            tag=filters.tag,
            favorite=filters.favorite,
            status=filters.status,
            limit=1_000_000,
        )
        ids = [item.id for item in QueryService(self.settings).list_papers(query_filters)]
        return [paper for paper_id in ids if (paper := session.get(Paper, paper_id))]

    def _write_csv(self, session: Session, output: Path, papers: list[Paper]) -> None:
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "id",
                    "title",
                    "doi",
                    "publication_year",
                    "venue",
                    "authors",
                    "sources",
                    "source_urls",
                    "status",
                    "favorite",
                    "rating",
                    "tags",
                    "abstract",
                ],
            )
            writer.writeheader()
            for paper in papers:
                library_item = self._library_item(session, paper.id)
                writer.writerow(
                    {
                        "id": paper.id,
                        "title": paper.title,
                        "doi": paper.doi,
                        "publication_year": paper.publication_year,
                        "venue": paper.venue.name if paper.venue else "",
                        "authors": "; ".join(self._authors(session, paper.id)),
                        "sources": "; ".join(self._source_names(session, paper.id)),
                        "source_urls": "; ".join(self._source_urls(session, paper.id)),
                        "status": self._status(library_item),
                        "favorite": bool(library_item.favorite) if library_item else False,
                        "rating": library_item.rating if library_item else "",
                        "tags": "; ".join(self._tags(session, paper.id)),
                        "abstract": paper.abstract or "",
                    }
                )

    def _render_ris(self, session: Session, papers: list[Paper]) -> str:
        blocks = []
        for paper in papers:
            lines = ["TY  - JOUR"]
            self._append_ris(lines, "TI", paper.title)
            for author in self._authors(session, paper.id):
                self._append_ris(lines, "AU", author)
            self._append_ris(lines, "PY", paper.publication_year)
            self._append_ris(lines, "JO", paper.venue.name if paper.venue else None)
            self._append_ris(lines, "DO", paper.doi_normalized or paper.doi)
            self._append_ris(lines, "UR", self._first_source_url(session, paper.id))
            self._append_ris(lines, "AB", paper.abstract)
            lines.append("ER  -")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks) + ("\n" if blocks else "")

    def _render_bibtex(self, session: Session, papers: list[Paper]) -> str:
        entries = []
        used_keys: set[str] = set()
        for paper in papers:
            key = self._citation_key(session, paper, used_keys)
            fields = {
                "title": paper.title,
                "author": " and ".join(self._authors(session, paper.id)),
                "year": str(paper.publication_year) if paper.publication_year else None,
                "journal": paper.venue.name if paper.venue else None,
                "doi": paper.doi_normalized or paper.doi,
                "url": self._first_source_url(session, paper.id),
                "abstract": paper.abstract,
            }
            lines = [f"@article{{{key},"]
            for name, value in fields.items():
                if value:
                    lines.append(f"  {name} = {{{self._escape_bibtex(value)}}},")
            lines.append("}")
            entries.append("\n".join(lines))
        return "\n\n".join(entries) + ("\n" if entries else "")

    def _citation_key(self, session: Session, paper: Paper, used_keys: set[str]) -> str:
        authors = self._authors(session, paper.id)
        last_name = re.sub(r"[^A-Za-z0-9]", "", authors[0].split()[-1]) if authors else ""
        words = [
            re.sub(r"[^A-Za-z0-9]", "", word).lower()
            for word in paper.title.split()
            if len(re.sub(r"[^A-Za-z0-9]", "", word)) > 3
        ]
        key = f"{last_name}{paper.publication_year or ''}{words[0] if words else ''}"
        key = key or f"refport_{paper.id}"
        candidate = key
        suffix = 2
        while candidate in used_keys:
            candidate = f"{key}{suffix}"
            suffix += 1
        used_keys.add(candidate)
        return candidate

    def _append_ris(self, lines: list[str], key: str, value: object | None) -> None:
        if value:
            lines.append(f"{key}  - {value}")

    def _escape_bibtex(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")

    def _library_item(self, session: Session, paper_id: int | None) -> LibraryItem | None:
        if paper_id is None:
            return None
        return session.exec(
            select(LibraryItem).where(LibraryItem.paper_id == paper_id)
        ).first()

    def _status(self, library_item: LibraryItem | None) -> str:
        if not library_item:
            return LibraryStatus.unread.value
        return (
            library_item.status.value
            if hasattr(library_item.status, "value")
            else str(library_item.status)
        )

    def _authors(self, session: Session, paper_id: int | None) -> list[str]:
        if paper_id is None:
            return []
        links = session.exec(
            select(PaperAuthor)
            .where(PaperAuthor.paper_id == paper_id)
            .order_by(PaperAuthor.author_order)
        ).all()
        return [link.author.name for link in links if link.author]

    def _source_names(self, session: Session, paper_id: int | None) -> list[str]:
        return sorted({source.source for source in self._sources(session, paper_id)})

    def _source_urls(self, session: Session, paper_id: int | None) -> list[str]:
        return [
            source.source_url
            for source in self._sources(session, paper_id)
            if source.source_url
        ]

    def _first_source_url(self, session: Session, paper_id: int | None) -> str | None:
        urls = self._source_urls(session, paper_id)
        return urls[0] if urls else None

    def _sources(self, session: Session, paper_id: int | None) -> list[PaperSource]:
        if paper_id is None:
            return []
        return session.exec(
            select(PaperSource).where(PaperSource.paper_id == paper_id)
        ).all()

    def _tags(self, session: Session, paper_id: int | None) -> list[str]:
        if paper_id is None:
            return []
        links = session.exec(select(PaperTag).where(PaperTag.paper_id == paper_id)).all()
        tags = [session.get(Tag, link.tag_id) for link in links]
        return sorted([tag.name for tag in tags if tag], key=str.lower)
