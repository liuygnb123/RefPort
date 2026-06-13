import hashlib

from sqlmodel import Session, select

from litsearch.browser.downloads import BrowserDownloadWatcher
from litsearch.browser.harness import detect_login_state
from litsearch.config import Settings
from litsearch.db.session import create_db_engine, init_database
from litsearch.models import Download, DownloadStatus, Paper
from litsearch.services.browser_service import BrowserService


def test_detect_login_state_from_html_markers():
    assert (
        detect_login_state("<a>Sign in</a>", login_text="sign in") == "login_required"
    )
    assert (
        detect_login_state("<span>My institution</span>", authenticated_text="institution")
        == "authenticated"
    )
    assert detect_login_state("<main>Search</main>", login_text="sign in") == "unknown"


def test_download_watcher_ignores_temporary_files(tmp_path):
    (tmp_path / "paper.pdf").write_bytes(b"%PDF-1.7\n")
    (tmp_path / "paper.pdf.crdownload").write_bytes(b"partial")
    (tmp_path / ".hidden").write_bytes(b"hidden")

    files = BrowserDownloadWatcher(tmp_path).list_completed()

    assert [item.path.name for item in files] == ["paper.pdf"]
    assert files[0].size_bytes == 9


def test_archive_download_records_file_hash(tmp_path):
    db_path = tmp_path / "litsearch.db"
    settings = Settings(db_url=f"sqlite:///{db_path}", _env_file=None)
    init_database(settings)
    engine = create_db_engine(settings)
    with Session(engine) as session:
        paper = Paper(title="Browser Download Paper")
        session.add(paper)
        session.commit()
        session.refresh(paper)
        paper_id = paper.id

    file_path = tmp_path / "download.pdf"
    content = b"%PDF-1.7\nbrowser download"
    file_path.write_bytes(content)

    archived = BrowserService(settings).archive_download(paper_id, file_path)

    with Session(engine) as session:
        download = session.exec(select(Download)).one()

    assert archived.sha256 == hashlib.sha256(content).hexdigest()
    assert archived.size_bytes == len(content)
    assert download.paper_id == paper_id
    assert download.status == DownloadStatus.downloaded
    assert download.file_path == str(file_path.resolve())
    assert download.source == "browser"
    assert download.size_bytes == len(content)
