from sqlmodel import Session, SQLModel, create_engine, select

from litsearch.connectors.base import SourcePaper
from litsearch.models import Author, Paper
from litsearch.services.persistence import upsert_source_paper


def test_upsert_source_paper_dedupes_by_doi():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        first = SourcePaper(source="openalex", title="First", doi="10.1/example")
        second = SourcePaper(source="crossref", title="Second", doi="https://doi.org/10.1/EXAMPLE")

        upsert_source_paper(session, first)
        upsert_source_paper(session, second)
        session.commit()

        papers = session.exec(select(Paper)).all()

    assert len(papers) == 1
    assert papers[0].title == "First"


def test_upsert_source_paper_dedupes_by_title_and_year_without_doi():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        first = SourcePaper(source="openalex", title="Circular Supply Chain", publication_year=2024)
        second = SourcePaper(
            source="crossref",
            title=" circular   supply chain ",
            publication_year=2024,
        )

        upsert_source_paper(session, first)
        upsert_source_paper(session, second)
        session.commit()

        assert len(session.exec(select(Paper)).all()) == 1


def test_upsert_source_paper_does_not_overwrite_existing_non_empty_fields():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        first = SourcePaper(
            source="openalex",
            title="Original",
            doi="10.1/example",
            abstract="Existing",
            authors=["Ada Lovelace", "Ada Lovelace"],
        )
        second = SourcePaper(
            source="crossref",
            title="Replacement",
            doi="10.1/example",
            abstract="New",
            authors=["Grace Hopper"],
        )

        upsert_source_paper(session, first)
        upsert_source_paper(session, second)
        session.commit()

        paper = session.exec(select(Paper)).one()
        authors = session.exec(select(Author)).all()

    assert paper.title == "Original"
    assert paper.abstract == "Existing"
    assert len(authors) == 1
