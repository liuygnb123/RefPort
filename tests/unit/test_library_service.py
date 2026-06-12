import pytest
from sqlmodel import Session

from litsearch.config import Settings
from litsearch.db.session import create_db_engine, init_database
from litsearch.exceptions import LitSearchValidationError
from litsearch.models import LibraryStatus, Paper
from litsearch.services.library_service import LibraryService


def _settings(tmp_path):
    return Settings(db_url=f"sqlite:///{tmp_path / 'test.db'}", _env_file=None)


def _paper(settings):
    init_database(settings)
    with Session(create_db_engine(settings)) as session:
        paper = Paper(title="Circular Supply Chain", publication_year=2024)
        session.add(paper)
        session.commit()
        session.refresh(paper)
        return paper.id


def test_library_add_update_remove(tmp_path):
    settings = _settings(tmp_path)
    paper_id = _paper(settings)
    service = LibraryService(settings)

    added = service.add_or_update_library_item(
        paper_id,
        status=LibraryStatus.reading,
        favorite=True,
        rating=4,
        notes="Important",
    )
    updated = service.update_library_item(
        paper_id,
        status=LibraryStatus.read,
        favorite=False,
        rating=5,
        notes="Done",
        rating_set=True,
        notes_set=True,
    )
    removed = service.remove_library_item(paper_id)

    assert added.favorite is True
    assert updated.status == "read"
    assert updated.rating == 5
    assert removed is True


def test_tags_are_idempotent_and_can_be_assigned(tmp_path):
    settings = _settings(tmp_path)
    paper_id = _paper(settings)
    service = LibraryService(settings)

    first = service.add_tag("Circular Economy")
    second = service.add_tag(" circular economy ")
    assigned = service.tag_paper(paper_id, "Circular Economy")
    tags = service.list_tags()
    untagged = service.untag_paper(paper_id, "Circular Economy")
    removed = service.remove_tag("Circular Economy")

    assert first.id == second.id
    assert assigned.paper_count == 1
    assert tags[0].paper_count == 1
    assert untagged is True
    assert removed is True


def test_invalid_paper_and_rating_raise_validation_error(tmp_path):
    settings = _settings(tmp_path)
    service = LibraryService(settings)

    with pytest.raises(LitSearchValidationError):
        service.add_or_update_library_item(999)

    paper_id = _paper(settings)
    with pytest.raises(LitSearchValidationError):
        service.add_or_update_library_item(paper_id, rating=6)
