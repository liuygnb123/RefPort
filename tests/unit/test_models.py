from sqlmodel import Session, SQLModel, create_engine, select

from litsearch.models import (
    Author,
    Download,
    DownloadStatus,
    Paper,
    PaperAuthor,
    PaperSource,
    SearchResultItem,
    SearchRun,
    SearchRunStatus,
    Venue,
)


def test_models_can_be_created_and_related():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        venue = Venue(name="Journal of Tests", name_normalized="journal of tests")
        paper = Paper(title="Circular Supply Chains", venue=venue)
        author = Author(name="Ada Lovelace")
        session.add(venue)
        session.add(paper)
        session.add(author)
        session.commit()

        link = PaperAuthor(paper_id=paper.id, author_id=author.id, author_order=1)
        source = PaperSource(paper_id=paper.id, source="crossref", raw_json="{}")
        search_run = SearchRun(
            query="circular supply chain",
            sources="crossref",
            status=SearchRunStatus.succeeded,
        )
        download = Download(paper_id=paper.id, status=DownloadStatus.skipped)
        session.add(link)
        session.add(source)
        session.add(search_run)
        session.add(download)
        session.commit()

        result_item = SearchResultItem(
            search_run_id=search_run.id,
            paper_id=paper.id,
            source="crossref",
            rank=1,
        )
        session.add(result_item)
        session.commit()

        stored = session.exec(select(Paper).where(Paper.title == "Circular Supply Chains")).one()
        venue_id = venue.id
        author_id = author.id
        link_id = link.id
        source_id = source.id
        search_status = search_run.status
        download_status = download.status
        result_item_id = result_item.id

    assert stored.id is not None
    assert venue_id is not None
    assert author_id is not None
    assert link_id is not None
    assert source_id is not None
    assert search_status == SearchRunStatus.succeeded
    assert download_status == DownloadStatus.skipped
    assert result_item_id is not None
