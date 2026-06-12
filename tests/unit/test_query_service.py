from sqlmodel import Session

from litsearch.config import Settings
from litsearch.db.session import create_db_engine, init_database
from litsearch.models import Paper, PaperSource, SearchResultItem, SearchRun, SearchRunStatus, Venue
from litsearch.services.library_service import LibraryService
from litsearch.services.query_service import PaperFilters, QueryService


def _settings(tmp_path):
    return Settings(db_url=f"sqlite:///{tmp_path / 'test.db'}", _env_file=None)


def _populate(settings):
    init_database(settings)
    with Session(create_db_engine(settings)) as session:
        venue = Venue(name="Journal of Circularity", name_normalized="journal of circularity")
        paper = Paper(
            title="Circular Supply Chain",
            publication_year=2024,
            doi="10.1/circular",
            abstract="Supply chain abstract",
            venue=venue,
        )
        session.add(paper)
        session.commit()
        session.refresh(paper)
        run = SearchRun(
            query="circular",
            sources="openalex",
            status=SearchRunStatus.succeeded,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        session.add(PaperSource(paper_id=paper.id, source="openalex", source_url="https://x"))
        session.add(
            SearchResultItem(
                search_run_id=run.id,
                paper_id=paper.id,
                source="openalex",
                rank=1,
            )
        )
        session.commit()
        return paper.id, run.id


def test_query_service_lists_searches_and_papers_with_filters(tmp_path):
    settings = _settings(tmp_path)
    paper_id, run_id = _populate(settings)
    library = LibraryService(settings)
    library.add_or_update_library_item(paper_id, favorite=True)
    library.tag_paper(paper_id, "circular-economy")

    service = QueryService(settings)
    runs = service.list_search_runs()
    run = service.get_search_run(run_id)
    papers = service.list_papers(
        PaperFilters(
            query="supply",
            source="openalex",
            year_from=2020,
            year_to=2025,
            tag="circular-economy",
            favorite=True,
        )
    )
    detail = service.get_paper(paper_id)

    assert runs[0].result_count == 1
    assert run.papers[0].id == paper_id
    assert papers[0].title == "Circular Supply Chain"
    assert detail.venue == "Journal of Circularity"
    assert detail.source_urls == ["https://x"]


def test_query_service_returns_none_for_missing_records(tmp_path):
    service = QueryService(_settings(tmp_path))

    assert service.get_search_run(999) is None
    assert service.get_paper(999) is None
