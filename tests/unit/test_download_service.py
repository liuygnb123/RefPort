import hashlib
import json
from pathlib import Path

import pytest
from sqlmodel import Session

from litsearch.config import Settings
from litsearch.db.session import create_db_engine, init_database
from litsearch.exceptions import LitSearchValidationError
from litsearch.models import Download, DownloadStatus, Paper, PaperSource
from litsearch.services.download_service import DownloadService


class FakeDownloadHttpClient:
    def __init__(self):
        self.bytes_by_url = {}
        self.text_by_url = {}
        self.json_by_url = {}
        self.byte_calls = []

    def get_bytes(self, url):
        self.byte_calls.append(url)
        value = self.bytes_by_url[url]
        if isinstance(value, Exception):
            raise value
        return value

    def get_text(self, url):
        value = self.text_by_url[url]
        if isinstance(value, Exception):
            raise value
        return value

    def get_json(self, url, params=None):
        return self.json_by_url[url]


@pytest.fixture()
def settings(tmp_path):
    db_path = tmp_path / "litsearch.db"
    return Settings(
        db_url=f"sqlite:///{db_path}",
        paper_dir=tmp_path / "papers",
        contact_email="me@example.com",
        _env_file=None,
    )


def add_paper(settings, *, doi=None, year=2024, source_url=None, raw=None):
    init_database(settings)
    engine = create_db_engine(settings)
    with Session(engine) as session:
        paper = Paper(title="OA Paper", doi=doi, publication_year=year)
        session.add(paper)
        session.commit()
        session.refresh(paper)
        if source_url or raw is not None:
            session.add(
                PaperSource(
                    paper_id=paper.id,
                    source="openalex",
                    source_url=source_url,
                    raw_json=json.dumps(raw or {}),
                )
            )
            session.commit()
        return paper.id


def test_download_missing_paper_fails(settings):
    with pytest.raises(LitSearchValidationError, match="Paper not found"):
        DownloadService(settings, FakeDownloadHttpClient()).download_paper(999)


def test_download_without_open_pdf_is_skipped(settings):
    paper_id = add_paper(settings, doi=None, source_url=None, raw=None)

    result = DownloadService(settings, FakeDownloadHttpClient()).download_paper(paper_id)

    assert result.status == DownloadStatus.skipped
    assert result.error == "No open-access PDF URL found"


def test_download_saves_pdf_from_magic_bytes(settings):
    pdf_url = "https://example.org/paper"
    client = FakeDownloadHttpClient()
    client.bytes_by_url[pdf_url] = (b"%PDF-1.7\nhello", "application/octet-stream")
    paper_id = add_paper(settings, raw={"pdf_url": pdf_url})

    result = DownloadService(settings, client).download_paper(paper_id)

    assert result.status == DownloadStatus.downloaded
    assert result.attempted_urls == [pdf_url]
    assert result.sha256 == hashlib.sha256(b"%PDF-1.7\nhello").hexdigest()
    assert result.size_bytes == len(b"%PDF-1.7\nhello")
    assert result.mime_type == "application/octet-stream"
    assert result.file_path is not None
    assert Path(result.file_path).read_bytes() == b"%PDF-1.7\nhello"
    assert Path(result.file_path).with_name("metadata.json").is_file()


def test_download_rejects_non_pdf_response(settings):
    pdf_url = "https://example.org/not-pdf"
    client = FakeDownloadHttpClient()
    client.bytes_by_url[pdf_url] = (b"<html>nope</html>", "text/html")
    paper_id = add_paper(settings, raw={"pdf_url": pdf_url})

    result = DownloadService(settings, client).download_paper(paper_id)

    assert result.status == DownloadStatus.failed
    assert result.attempted_urls == [pdf_url]
    assert "not a PDF" in (result.error or "")


def test_existing_download_is_reused_without_force(settings):
    pdf_url = "https://example.org/paper.pdf"
    client = FakeDownloadHttpClient()
    client.bytes_by_url[pdf_url] = (b"%PDF-1.7\nfirst", "application/pdf")
    paper_id = add_paper(settings, raw={"pdf_url": pdf_url})
    first = DownloadService(settings, client).download_paper(paper_id)

    second = DownloadService(settings, client).download_paper(paper_id)

    assert second.id == first.id
    assert client.byte_calls == [pdf_url]


def test_force_download_creates_new_record(settings):
    pdf_url = "https://example.org/paper.pdf"
    client = FakeDownloadHttpClient()
    client.bytes_by_url[pdf_url] = (b"%PDF-1.7\nfirst", "application/pdf")
    paper_id = add_paper(settings, raw={"pdf_url": pdf_url})
    first = DownloadService(settings, client).download_paper(paper_id)
    client.bytes_by_url[pdf_url] = (b"%PDF-1.7\nsecond", "application/pdf")

    second = DownloadService(settings, client).download_paper(paper_id, force=True)

    assert second.id != first.id
    assert second.sha256 == hashlib.sha256(b"%PDF-1.7\nsecond").hexdigest()
    assert client.byte_calls == [pdf_url, pdf_url]


def test_landing_page_meta_pdf_url_is_candidate(settings):
    landing_url = "https://example.org/landing"
    pdf_url = "https://cdn.example.org/paper.pdf"
    client = FakeDownloadHttpClient()
    client.text_by_url[landing_url] = (
        f'<html><meta name="citation_pdf_url" content="{pdf_url}"></html>',
        "text/html",
    )
    client.bytes_by_url[pdf_url] = (b"%PDF-1.7\nlanding", "application/pdf")
    paper_id = add_paper(settings, source_url=landing_url, raw={})

    result = DownloadService(settings, client).download_paper(paper_id)

    assert result.status == DownloadStatus.downloaded
    assert result.pdf_url == pdf_url


def test_landing_page_pdf_link_is_candidate(settings):
    landing_url = "https://example.org/landing"
    pdf_url = "https://example.org/content/paper.pdf"
    client = FakeDownloadHttpClient()
    client.text_by_url[landing_url] = (
        '<html><a href="/content/paper.pdf" data-article-pdf="true">PDF</a></html>',
        "text/html",
    )
    client.bytes_by_url[pdf_url] = (b"%PDF-1.7\nlink", "application/pdf")
    paper_id = add_paper(settings, source_url=landing_url, raw={})

    result = DownloadService(settings, client).download_paper(paper_id)

    assert result.status == DownloadStatus.downloaded
    assert result.pdf_url == pdf_url


def test_unpaywall_pdf_url_is_candidate(settings):
    pdf_url = "https://example.org/unpaywall.pdf"
    client = FakeDownloadHttpClient()
    client.json_by_url["https://api.unpaywall.org/v2/10.1234%2Fexample"] = {
        "best_oa_location": {"url_for_pdf": pdf_url}
    }
    client.bytes_by_url[pdf_url] = (b"%PDF-1.7\nunpaywall", "application/pdf")
    paper_id = add_paper(settings, doi="10.1234/example")

    result = DownloadService(settings, client).download_paper(paper_id)

    assert result.status == DownloadStatus.downloaded
    assert result.source == "unpaywall"


def test_openalex_doi_pdf_url_is_candidate_without_email(tmp_path):
    db_path = tmp_path / "litsearch.db"
    settings = Settings(
        db_url=f"sqlite:///{db_path}",
        paper_dir=tmp_path / "papers",
        _env_file=None,
    )
    pdf_url = "https://repo.example.org/openalex.pdf"
    client = FakeDownloadHttpClient()
    openalex_url = "https://api.openalex.org/works/doi:https%3A%2F%2Fdoi.org%2F10.1234%2Fexample"
    client.json_by_url[openalex_url] = {
        "id": "https://openalex.org/W1",
        "primary_location": {"pdf_url": pdf_url},
    }
    client.bytes_by_url[pdf_url] = (b"%PDF-1.7\nopenalex", "application/pdf")
    paper_id = add_paper(settings, doi="10.1234/example")

    result = DownloadService(settings, client).download_paper(paper_id)

    assert result.status == DownloadStatus.downloaded
    assert result.source == "openalex"
    assert result.source_url == "https://openalex.org/W1"


def test_openalex_doi_candidates_continue_after_non_pdf(settings):
    first_url = "https://publisher.example.org/paper.pdf"
    second_url = "https://repo.example.org/paper.pdf"
    client = FakeDownloadHttpClient()
    client.json_by_url["https://api.unpaywall.org/v2/10.5678%2Fexample"] = {}
    openalex_url = "https://api.openalex.org/works/doi:https%3A%2F%2Fdoi.org%2F10.5678%2Fexample"
    client.json_by_url[openalex_url] = {
        "id": "https://openalex.org/W2",
        "primary_location": {"pdf_url": first_url},
        "locations": [{"pdf_url": second_url}],
    }
    client.bytes_by_url[first_url] = (b"<html>challenge</html>", "text/html")
    client.bytes_by_url[second_url] = (b"%PDF-1.7\nrepository", "application/pdf")
    paper_id = add_paper(settings, doi="10.5678/example")

    result = DownloadService(settings, client).download_paper(paper_id)

    assert result.status == DownloadStatus.downloaded
    assert result.pdf_url == second_url
    assert result.attempted_urls == [first_url, second_url]


def test_list_and_get_downloads(settings):
    paper_id = add_paper(settings)
    init_database(settings)
    engine = create_db_engine(settings)
    with Session(engine) as session:
        download = Download(paper_id=paper_id, status=DownloadStatus.skipped)
        session.add(download)
        session.commit()
        session.refresh(download)
        download_id = download.id

    service = DownloadService(settings, FakeDownloadHttpClient())

    assert service.list_downloads()[0].id == download_id
    assert service.get_download(download_id).paper_id == paper_id
