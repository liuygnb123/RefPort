import csv

from sqlmodel import Session

from litsearch.config import Settings
from litsearch.db.session import create_db_engine, init_database
from litsearch.models import (
    Author,
    Paper,
    PaperAuthor,
    PaperSource,
    SearchResultItem,
    SearchRun,
    SearchRunStatus,
    Venue,
)
from litsearch.services.export_service import ExportFilters, ExportService
from litsearch.services.library_service import LibraryService


def _settings(tmp_path):
    return Settings(db_url=f"sqlite:///{tmp_path / 'test.db'}", _env_file=None)


def _populate(settings):
    init_database(settings)
    with Session(create_db_engine(settings)) as session:
        venue = Venue(name="Journal of Tests", name_normalized="journal of tests")
        paper = Paper(
            title="Circular Supply Chain",
            doi="10.1/CIRCULAR",
            doi_normalized="10.1/circular",
            publication_year=2024,
            abstract="Abstract text",
            venue=venue,
        )
        author = Author(name="Ada Lovelace", name_normalized="ada lovelace")
        session.add(paper)
        session.add(author)
        session.commit()
        session.refresh(paper)
        session.refresh(author)
        session.add(PaperAuthor(paper_id=paper.id, author_id=author.id, author_order=1))
        session.add(
            PaperSource(
                paper_id=paper.id,
                source="openalex",
                source_url="https://example.test/paper",
                raw_json='{"private": false}',
            )
        )
        run = SearchRun(
            query="circular",
            sources="openalex",
            status=SearchRunStatus.succeeded,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
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


def test_export_service_writes_csv_bibtex_and_ris(tmp_path):
    settings = _settings(tmp_path)
    paper_id, run_id = _populate(settings)
    library = LibraryService(settings)
    library.add_or_update_library_item(paper_id, favorite=True, rating=4)
    library.tag_paper(paper_id, "circular-economy")
    service = ExportService(settings)

    csv_path = tmp_path / "out" / "refs.csv"
    bib_path = tmp_path / "refs.bib"
    ris_path = tmp_path / "refs.ris"

    csv_summary = service.export_papers("csv", csv_path, ExportFilters(tag="circular-economy"))
    bib_summary = service.export_papers(
        "bibtex",
        bib_path,
        ExportFilters(paper_ids=[paper_id]),
    )
    ris_summary = service.export_papers(
        "ris",
        ris_path,
        ExportFilters(search_run_id=run_id),
    )

    with csv_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert csv_summary.paper_count == 1
    assert rows[0]["title"] == "Circular Supply Chain"
    assert rows[0]["tags"] == "circular-economy"
    assert "raw_json" not in rows[0]
    assert bib_summary.paper_count == 1
    assert "@article{Lovelace2024circular" in bib_path.read_text(encoding="utf-8")
    assert "author = {Ada Lovelace}" in bib_path.read_text(encoding="utf-8")
    assert ris_summary.paper_count == 1
    assert "TY  - JOUR" in ris_path.read_text(encoding="utf-8")
    assert "DO  - 10.1/circular" in ris_path.read_text(encoding="utf-8")


def test_export_service_filters_favorites(tmp_path):
    settings = _settings(tmp_path)
    _populate(settings)
    summary = ExportService(settings).export_papers(
        "csv",
        tmp_path / "none.csv",
        ExportFilters(favorite=True),
    )

    assert summary.paper_count == 0
