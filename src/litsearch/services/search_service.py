"""Search orchestration service."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlmodel import Session

from litsearch.config import Settings
from litsearch.connectors.base import SearchRequest, SourcePaper
from litsearch.connectors.crossref import CrossrefConnector
from litsearch.connectors.openalex import OpenAlexConnector
from litsearch.connectors.unpaywall import UnpaywallConnector
from litsearch.db.session import create_db_engine, init_database
from litsearch.exceptions import LitSearchValidationError
from litsearch.models import Paper, SearchResultItem, SearchRun, SearchRunStatus
from litsearch.normalization import normalize_doi
from litsearch.services.persistence import upsert_source_paper

SEARCH_SOURCE_IDS = {"openalex", "crossref"}
DEFAULT_SEARCH_SOURCES = ["openalex", "crossref"]


class PaperSummary(BaseModel):
    id: int
    title: str
    doi: str | None = None
    publication_year: int | None = None
    source: str
    source_url: str | None = None
    pdf_url: str | None = None
    is_open_access: bool | None = None


class SearchSummary(BaseModel):
    search_run_id: int
    query: str
    sources: list[str]
    status: str
    total_raw: int
    total_saved: int
    total_deduped: int
    errors: dict[str, str]
    papers: list[PaperSummary]


class SearchService:
    def __init__(
        self,
        settings: Settings,
        connectors: dict[str, object] | None = None,
        unpaywall_connector: UnpaywallConnector | None = None,
    ):
        self.settings = settings
        self.connectors = connectors or {
            "openalex": OpenAlexConnector(settings),
            "crossref": CrossrefConnector(settings),
        }
        self.unpaywall_connector = unpaywall_connector or UnpaywallConnector(settings)

    def search(
        self,
        query: str,
        sources: list[str] | None = None,
        limit: int = 10,
        enrich_unpaywall: bool = True,
    ) -> SearchSummary:
        selected_sources = sources or DEFAULT_SEARCH_SOURCES
        invalid = [source for source in selected_sources if source not in SEARCH_SOURCE_IDS]
        if invalid:
            raise LitSearchValidationError(
                "Unsupported search source(s): "
                f"{', '.join(invalid)}. Phase 1 supports: openalex, crossref."
            )
        if limit < 1:
            raise LitSearchValidationError("limit must be greater than 0")

        init_database(self.settings)
        engine = create_db_engine(self.settings)
        started = datetime.now(UTC).isoformat()
        errors: dict[str, str] = {}
        papers: list[PaperSummary] = []
        total_raw = 0
        total_saved = 0
        seen_paper_ids: set[int] = set()

        with Session(engine) as session:
            search_run = SearchRun(
                query=query,
                sources=",".join(selected_sources),
                status=SearchRunStatus.running,
                started_at=started,
            )
            session.add(search_run)
            session.commit()
            session.refresh(search_run)

            for source in selected_sources:
                connector = self.connectors[source]
                try:
                    source_papers = connector.search(SearchRequest(query=query, limit=limit))
                except Exception as exc:  # noqa: BLE001 - source failures should be isolated
                    errors[source] = str(exc)
                    continue

                total_raw += len(source_papers)
                for rank, source_paper in enumerate(source_papers, start=1):
                    enriched = self._enrich(source_paper, enrich_unpaywall, errors)
                    paper = upsert_source_paper(session, enriched)
                    session.add(
                        SearchResultItem(
                            search_run_id=search_run.id,
                            paper_id=paper.id,
                            source=source,
                            rank=rank,
                        )
                    )
                    session.flush()
                    total_saved += 1
                    seen_paper_ids.add(paper.id)
                    papers.append(self._paper_summary(paper, enriched))

            succeeded = total_saved > 0
            search_run.status = SearchRunStatus.succeeded if succeeded else SearchRunStatus.failed
            search_run.finished_at = datetime.now(UTC).isoformat()
            search_run.errors = (
                json.dumps(errors, ensure_ascii=False, sort_keys=True) if errors else None
            )
            session.add(search_run)
            session.commit()
            status = search_run.status.value
            search_run_id = search_run.id

        return SearchSummary(
            search_run_id=search_run_id,
            query=query,
            sources=selected_sources,
            status=status,
            total_raw=total_raw,
            total_saved=total_saved,
            total_deduped=total_raw - len(seen_paper_ids),
            errors=errors,
            papers=papers[: limit * len(selected_sources)],
        )

    def _enrich(
        self,
        source_paper: SourcePaper,
        enrich_unpaywall: bool,
        errors: dict[str, str],
    ) -> SourcePaper:
        doi = normalize_doi(source_paper.doi)
        if not enrich_unpaywall or not doi or not self.settings.source_email("unpaywall"):
            return source_paper
        try:
            unpaywall_paper = self.unpaywall_connector.lookup_by_doi(doi)
        except Exception as exc:  # noqa: BLE001 - enrichment is optional
            errors.setdefault("unpaywall", str(exc))
            return source_paper
        if not unpaywall_paper:
            return source_paper
        data = source_paper.model_dump()
        data["pdf_url"] = source_paper.pdf_url or unpaywall_paper.pdf_url
        data["is_open_access"] = (
            source_paper.is_open_access
            if source_paper.is_open_access is not None
            else unpaywall_paper.is_open_access
        )
        return SourcePaper(**data)

    def _paper_summary(self, paper: Paper, source_paper: SourcePaper) -> PaperSummary:
        return PaperSummary(
            id=paper.id,
            title=paper.title,
            doi=paper.doi,
            publication_year=paper.publication_year,
            source=source_paper.source,
            source_url=source_paper.source_url,
            pdf_url=source_paper.pdf_url,
            is_open_access=source_paper.is_open_access,
        )
