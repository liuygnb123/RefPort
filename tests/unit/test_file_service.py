import pytest
from sqlmodel import Session

from litsearch.config import Settings
from litsearch.db.session import create_db_engine, init_database
from litsearch.exceptions import LitSearchValidationError
from litsearch.models import Download, DownloadStatus, Paper
from litsearch.services.file_service import FileService


@pytest.fixture()
def settings(tmp_path):
    return Settings(db_url=f"sqlite:///{tmp_path / 'litsearch.db'}", _env_file=None)


def test_files_list_returns_existing_downloaded_files(settings, tmp_path):
    init_database(settings)
    engine = create_db_engine(settings)
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n")
    with Session(engine) as session:
        paper = Paper(title="Downloaded", publication_year=2023)
        session.add(paper)
        session.commit()
        session.refresh(paper)
        session.add(
            Download(
                paper_id=paper.id,
                status=DownloadStatus.downloaded,
                file_path=str(pdf_path),
                size_bytes=9,
                sha256="abc",
            )
        )
        session.commit()

    files = FileService(settings).list_files()

    assert len(files) == 1
    assert files[0].file_path == pdf_path
    assert files[0].size_bytes == 9


def test_open_file_uses_macos_open_when_available(settings, tmp_path, monkeypatch):
    init_database(settings)
    engine = create_db_engine(settings)
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n")
    with Session(engine) as session:
        paper = Paper(title="Downloaded")
        session.add(paper)
        session.commit()
        session.refresh(paper)
        session.add(
            Download(
                paper_id=paper.id,
                status=DownloadStatus.downloaded,
                file_path=str(pdf_path),
            )
        )
        session.commit()
        paper_id = paper.id

    calls = []
    monkeypatch.setattr("litsearch.services.file_service.sys.platform", "darwin")
    monkeypatch.setattr(
        "litsearch.services.file_service.subprocess.run",
        lambda args, check=False: calls.append((args, check)),
    )

    opened = FileService(settings).open_file(paper_id)

    assert opened == pdf_path
    assert calls == [(["open", str(pdf_path)], False)]


def test_open_file_missing_download_fails(settings):
    init_database(settings)
    engine = create_db_engine(settings)
    with Session(engine) as session:
        paper = Paper(title="No File")
        session.add(paper)
        session.commit()
        session.refresh(paper)
        paper_id = paper.id

    with pytest.raises(LitSearchValidationError, match="No downloaded file"):
        FileService(settings).open_file(paper_id)
