import hashlib

import pytest
from sqlmodel import Session, select

from litsearch.browser.downloads import BrowserDownloadWatcher
from litsearch.browser.harness import detect_login_state
from litsearch.browser.parsers import detect_manual_block, parse_snapshot
from litsearch.config import Settings
from litsearch.db.session import create_db_engine, init_database
from litsearch.models import (
    BrowserImport,
    BrowserLoginState,
    BrowserSessionStatus,
    BrowserSnapshotRecord,
    Download,
    DownloadStatus,
    Paper,
    PaperSource,
)
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


def test_detect_manual_block_from_snapshot_html():
    assert (
        detect_manual_block("<main>Unusual traffic from your network</main>")
        == "unusual traffic"
    )
    assert detect_manual_block("<main>Results</main>") is None


def test_parse_generic_snapshot_reads_local_html(tmp_path):
    html_path = tmp_path / "snapshot.html"
    html_path.write_text(
        "<html><head><title>Ignored</title></head>"
        "<body><h1>Circular Supply Chain Review 2024</h1></body></html>",
        encoding="utf-8",
    )

    papers = parse_snapshot(html_path, "generic", base_url="https://example.com")

    assert papers[0].title == "Circular Supply Chain Review 2024"
    assert papers[0].year == 2024
    assert papers[0].source_url == "https://example.com"


def test_parse_google_scholar_minimal_snapshot_reads_links(tmp_path):
    html_path = tmp_path / "scholar.html"
    html_path.write_text(
        '<html><body><a href="/paper">Circular economy supply chains 2023</a></body></html>',
        encoding="utf-8",
    )

    papers = parse_snapshot(html_path, "google_scholar", base_url="https://scholar.google.com")

    assert papers[0].title == "Circular economy supply chains 2023"
    assert papers[0].year == 2023
    assert papers[0].source_url == "https://scholar.google.com/paper"
    assert papers[0].raw["minimal_parser"] is True


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


def test_browser_session_start_list_get(tmp_path):
    db_path = tmp_path / "litsearch.db"
    settings = Settings(db_url=f"sqlite:///{db_path}", _env_file=None)
    init_database(settings)

    service = BrowserService(settings)
    created = service.start_session("generic", "https://example.com")

    assert created.id is not None
    assert created.platform == "generic"
    assert service.get_session(created.id).entry_url == "https://example.com"
    assert [item.id for item in service.list_sessions()] == [created.id]


def test_parse_session_uses_latest_snapshot(tmp_path):
    db_path = tmp_path / "litsearch.db"
    html_path = tmp_path / "snapshot.html"
    html_path.write_text("<h1>Browser Parsed Paper 2024</h1>", encoding="utf-8")
    settings = Settings(db_url=f"sqlite:///{db_path}", _env_file=None)
    init_database(settings)
    engine = create_db_engine(settings)
    service = BrowserService(settings)
    session_record = service.start_session("generic", "https://example.com")
    with Session(engine) as session:
        session.add(
            BrowserSnapshotRecord(
                session_id=session_record.id,
                url="https://example.com",
                html_path=str(html_path),
                login_state=BrowserLoginState.unknown.value,
            )
        )
        session.commit()

    papers = service.parse_session(session_record.id)

    assert papers[0].title == "Browser Parsed Paper 2024"
    assert service.get_session(session_record.id).status == BrowserSessionStatus.parsed.value


def test_parse_session_refuses_blocked_snapshot(tmp_path):
    db_path = tmp_path / "litsearch.db"
    html_path = tmp_path / "snapshot.html"
    html_path.write_text("<h1>Blocked</h1>", encoding="utf-8")
    settings = Settings(db_url=f"sqlite:///{db_path}", _env_file=None)
    init_database(settings)
    engine = create_db_engine(settings)
    service = BrowserService(settings)
    session_record = service.start_session("generic", "https://example.com")
    with Session(engine) as session:
        session.add(
            BrowserSnapshotRecord(
                session_id=session_record.id,
                url="https://example.com",
                html_path=str(html_path),
                login_state=BrowserLoginState.blocked_manual_action_required.value,
                blocked_reason="captcha",
            )
        )
        session.commit()

    with pytest.raises(Exception, match="requires manual action"):
        service.parse_session(session_record.id)


def test_parse_session_refuses_login_required_snapshot(tmp_path):
    db_path = tmp_path / "litsearch.db"
    html_path = tmp_path / "snapshot.html"
    html_path.write_text("<h1>Sign in</h1>", encoding="utf-8")
    settings = Settings(db_url=f"sqlite:///{db_path}", _env_file=None)
    init_database(settings)
    engine = create_db_engine(settings)
    service = BrowserService(settings)
    session_record = service.start_session("generic", "https://example.com")
    with Session(engine) as session:
        session.add(
            BrowserSnapshotRecord(
                session_id=session_record.id,
                url="https://example.com",
                html_path=str(html_path),
                login_state=BrowserLoginState.login_required.value,
            )
        )
        session.commit()

    with pytest.raises(Exception, match="requires manual action"):
        service.parse_session(session_record.id)


def test_import_session_writes_paper_source_and_import_without_duplicates(tmp_path):
    db_path = tmp_path / "litsearch.db"
    html_path = tmp_path / "snapshot.html"
    html_path.write_text("<h1>Imported Browser Paper 2024</h1>", encoding="utf-8")
    settings = Settings(db_url=f"sqlite:///{db_path}", _env_file=None)
    init_database(settings)
    engine = create_db_engine(settings)
    service = BrowserService(settings)
    session_record = service.start_session("generic", "https://example.com")
    with Session(engine) as session:
        session.add(
            BrowserSnapshotRecord(
                session_id=session_record.id,
                url="https://example.com",
                html_path=str(html_path),
                login_state=BrowserLoginState.unknown.value,
            )
        )
        session.commit()

    first = service.import_session(session_record.id)
    second = service.import_session(session_record.id)

    with Session(engine) as session:
        papers = session.exec(select(Paper)).all()
        sources = session.exec(select(PaperSource)).all()
        imports = session.exec(select(BrowserImport)).all()

    assert first.imported_count == 1
    assert second.paper_ids == first.paper_ids
    assert len(papers) == 1
    assert sources[0].source == "generic"
    assert sources[0].raw_json is not None
    assert len(imports) == 1
