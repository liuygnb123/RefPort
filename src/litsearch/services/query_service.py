"""Read-only queries for search history and the paper library."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from litsearch.config import Settings
from litsearch.db.session import create_db_engine, init_database
from litsearch.models import (
    LibraryStatus,
    Paper,
    PaperAuthor,
    PaperSource,
    SearchResultItem,
    SearchRun,
    Tag,
)
from litsearch.models.library import LibraryItem, PaperTag
from litsearch.normalization import normalize_name


class SearchRunSummary(BaseModel):
    id: int
    query: str
    sources: list[str]
    status: str
    started_at: str | None
    finished_at: str | None
    result_count: int
    errors: dict[str, str] = Field(default_factory=dict)


class PaperFilters(BaseModel):
    query: str | None = None
    source: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    tag: str | None = None
    status: LibraryStatus | None = None
    favorite: bool = False
    limit: int = 50


class PaperListItem(BaseModel):
    id: int
    title: str
    year: int | None
    doi: str | None
    venue: str | None
    sources: list[str]
    status: str
    favorite: bool
    tags: list[str]


class SearchRunDetail(SearchRunSummary):
    papers: list[PaperListItem] = Field(default_factory=list)


class PaperDetail(PaperListItem):
    authors: list[str]
    abstract: str | None
    rating: int | None
    notes: str | None
    source_urls: list[str]


class QueryService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def list_search_runs(self, limit: int = 20) -> list[SearchRunSummary]:
        init_database(self.settings)
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            runs = session.exec(
                select(SearchRun).order_by(SearchRun.id.desc()).limit(limit)
            ).all()
            return [self._search_run_summary(session, run) for run in runs]

    def get_search_run(self, search_run_id: int) -> SearchRunDetail | None:
        init_database(self.settings)
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            run = session.get(SearchRun, search_run_id)
            if not run:
                return None
            items = session.exec(
                select(SearchResultItem)
                .where(SearchResultItem.search_run_id == search_run_id)
                .order_by(SearchResultItem.rank)
            ).all()
            summary = self._search_run_summary(session, run)
            papers = [
                self._paper_list_item(session, item.paper)
                for item in items
                if item.paper is not None
            ]
            return SearchRunDetail(**summary.model_dump(), papers=papers)

    def list_papers(self, filters: PaperFilters | None = None) -> list[PaperListItem]:
        init_database(self.settings)
        filters = filters or PaperFilters()
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            papers = session.exec(select(Paper).order_by(Paper.id)).all()
            results: list[PaperListItem] = []
            for paper in papers:
                if self._matches_filters(session, paper, filters):
                    results.append(self._paper_list_item(session, paper))
                if len(results) >= filters.limit:
                    break
            return results

    def get_paper(self, paper_id: int) -> PaperDetail | None:
        init_database(self.settings)
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            paper = session.get(Paper, paper_id)
            if not paper:
                return None
            base = self._paper_list_item(session, paper)
            library_item = self._library_item(session, paper.id)
            return PaperDetail(
                **base.model_dump(),
                authors=self._authors(session, paper.id),
                abstract=paper.abstract,
                rating=library_item.rating if library_item else None,
                notes=library_item.notes if library_item else None,
                source_urls=[
                    source.source_url
                    for source in self._paper_sources(session, paper.id)
                    if source.source_url
                ],
            )

    def _matches_filters(self, session: Session, paper: Paper, filters: PaperFilters) -> bool:
        library_item = self._library_item(session, paper.id)
        sources = self._paper_sources(session, paper.id)
        tags = self._tags(session, paper.id)

        if filters.query:
            needle = filters.query.lower()
            haystack = " ".join(
                value or ""
                for value in (paper.title, paper.abstract, paper.doi, paper.doi_normalized)
            ).lower()
            if needle not in haystack:
                return False
        if filters.source and filters.source.lower() not in {s.source.lower() for s in sources}:
            return False
        if filters.year_from and (paper.publication_year or 0) < filters.year_from:
            return False
        if filters.year_to and (paper.publication_year or 9999) > filters.year_to:
            return False
        if filters.tag:
            normalized = normalize_name(filters.tag)
            if normalized not in {normalize_name(tag) for tag in tags}:
                return False
        if filters.status and (not library_item or library_item.status != filters.status):
            return False
        if filters.favorite and (not library_item or not library_item.favorite):
            return False
        return True

    def _search_run_summary(self, session: Session, run: SearchRun) -> SearchRunSummary:
        result_count = len(
            session.exec(select(SearchResultItem).where(SearchResultItem.search_run_id == run.id))
            .all()
        )
        errors = json.loads(run.errors) if run.errors else {}
        return SearchRunSummary(
            id=run.id,
            query=run.query,
            sources=[source for source in run.sources.split(",") if source],
            status=run.status.value if hasattr(run.status, "value") else str(run.status),
            started_at=run.started_at,
            finished_at=run.finished_at,
            result_count=result_count,
            errors=errors,
        )

    def _paper_list_item(self, session: Session, paper: Paper) -> PaperListItem:
        library_item = self._library_item(session, paper.id)
        return PaperListItem(
            id=paper.id,
            title=paper.title,
            year=paper.publication_year,
            doi=paper.doi,
            venue=paper.venue.name if paper.venue else None,
            sources=sorted({source.source for source in self._paper_sources(session, paper.id)}),
            status=(library_item.status.value if library_item else LibraryStatus.unread.value),
            favorite=bool(library_item.favorite) if library_item else False,
            tags=self._tags(session, paper.id),
        )

    def _library_item(self, session: Session, paper_id: int | None) -> LibraryItem | None:
        if paper_id is None:
            return None
        return session.exec(
            select(LibraryItem).where(LibraryItem.paper_id == paper_id)
        ).first()

    def _paper_sources(self, session: Session, paper_id: int | None) -> list[PaperSource]:
        if paper_id is None:
            return []
        return session.exec(
            select(PaperSource).where(PaperSource.paper_id == paper_id)
        ).all()

    def _tags(self, session: Session, paper_id: int | None) -> list[str]:
        if paper_id is None:
            return []
        links = session.exec(select(PaperTag).where(PaperTag.paper_id == paper_id)).all()
        names = []
        for link in links:
            tag = session.get(Tag, link.tag_id)
            if tag:
                names.append(tag.name)
        return sorted(names, key=str.lower)

    def _authors(self, session: Session, paper_id: int | None) -> list[str]:
        if paper_id is None:
            return []
        links = session.exec(
            select(PaperAuthor)
            .where(PaperAuthor.paper_id == paper_id)
            .order_by(PaperAuthor.author_order)
        ).all()
        return [link.author.name for link in links if link.author]
