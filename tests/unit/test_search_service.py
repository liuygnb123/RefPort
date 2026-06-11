from sqlmodel import Session, select

from litsearch.config import Settings
from litsearch.connectors.base import SourcePaper
from litsearch.db.session import create_db_engine
from litsearch.models import Paper, PaperSource, SearchResultItem, SearchRun, SearchRunStatus
from litsearch.services.search_service import SearchService


class FakeConnector:
    def __init__(self, papers=None, error=None):
        self.papers = papers or []
        self.error = error

    def search(self, request):
        if self.error:
            raise self.error
        return self.papers


def test_search_service_single_source_failure_still_saves_other_results(tmp_path):
    settings = Settings(db_url=f"sqlite:///{tmp_path / 'test.db'}", _env_file=None)
    service = SearchService(
        settings,
        connectors={
            "openalex": FakeConnector(
                [SourcePaper(source="openalex", title="Circular Supply Chain", doi="10.1/a")]
            ),
            "crossref": FakeConnector(error=RuntimeError("crossref down")),
        },
    )

    summary = service.search("circular", ["openalex", "crossref"], limit=1)

    assert summary.status == "succeeded"
    assert summary.total_saved == 1
    assert "crossref" in summary.errors
    with Session(create_db_engine(settings)) as session:
        assert len(session.exec(select(Paper)).all()) == 1
        assert session.exec(select(SearchRun)).one().status == SearchRunStatus.succeeded


def test_search_service_all_sources_failed_sets_run_failed(tmp_path):
    settings = Settings(db_url=f"sqlite:///{tmp_path / 'test.db'}", _env_file=None)
    service = SearchService(
        settings,
        connectors={
            "openalex": FakeConnector(error=RuntimeError("openalex down")),
            "crossref": FakeConnector(error=RuntimeError("crossref down")),
        },
    )

    summary = service.search("circular", ["openalex", "crossref"], limit=1)

    assert summary.status == "failed"
    assert summary.total_saved == 0
    with Session(create_db_engine(settings)) as session:
        assert session.exec(select(SearchRun)).one().status == SearchRunStatus.failed


def test_search_service_supports_commercial_source_results(tmp_path):
    settings = Settings(db_url=f"sqlite:///{tmp_path / 'test.db'}", _env_file=None)
    service = SearchService(
        settings,
        connectors={
            "ieee": FakeConnector(
                [SourcePaper(source="ieee", title="Circular IEEE", doi="10.1/ieee")]
            ),
        },
    )

    summary = service.search("circular", ["ieee"], limit=1)

    assert summary.status == "succeeded"
    assert summary.total_saved == 1
    with Session(create_db_engine(settings)) as session:
        assert session.exec(select(PaperSource)).one().source == "ieee"
        assert session.exec(select(SearchResultItem)).one().source == "ieee"


def test_search_service_mixed_open_and_unconfigured_ieee_succeeds(tmp_path):
    settings = Settings(db_url=f"sqlite:///{tmp_path / 'test.db'}", _env_file=None)
    service = SearchService(
        settings,
        connectors={
            "openalex": FakeConnector(
                [SourcePaper(source="openalex", title="Circular Open", doi="10.1/open")]
            ),
            "ieee": FakeConnector(error=RuntimeError("IEEE Xplore API key is not configured")),
        },
    )

    summary = service.search("circular", ["openalex", "ieee"], limit=1)

    assert summary.status == "succeeded"
    assert summary.total_saved == 1
    assert "ieee" in summary.errors
