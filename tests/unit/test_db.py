from sqlmodel import Session, select

from litsearch.config import Settings
from litsearch.db.session import create_db_engine, init_database
from litsearch.models import Paper


def test_temporary_sqlite_can_be_initialized_and_used(tmp_path):
    db_path = tmp_path / "litsearch-test.db"
    settings = Settings(db_url=f"sqlite:///{db_path}", _env_file=None)

    revision = init_database(settings)
    engine = create_db_engine(settings)

    with Session(engine) as session:
        paper = Paper(title="Test Paper")
        session.add(paper)
        session.commit()
        stored = session.exec(select(Paper)).one()

    assert revision == "0004_download_files"
    assert stored.title == "Test Paper"
    assert db_path.exists()
    assert "./data/litsearch.db" not in str(db_path)
