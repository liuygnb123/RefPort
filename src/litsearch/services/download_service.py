"""Open-access PDF download service."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import httpx
from pydantic import BaseModel
from sqlmodel import Session, select

from litsearch.config import Settings
from litsearch.connectors.http import HttpClient
from litsearch.db.session import create_db_engine, init_database
from litsearch.exceptions import ConnectorError, LitSearchValidationError
from litsearch.models import Download, DownloadStatus, Paper, PaperSource
from litsearch.normalization import normalize_doi
from litsearch.services.file_service import FileService

UNPAYWALL_URL_TEMPLATE = "https://api.unpaywall.org/v2/{doi}"
OPENALEX_DOI_URL_TEMPLATE = "https://api.openalex.org/works/doi:{doi}"
PDF_KEYS = {"pdf_url", "url_for_pdf", "citation_pdf_url", "fulltext_pdf_url"}


class DownloadResult(BaseModel):
    id: int
    paper_id: int
    status: str
    source: str | None = None
    source_url: str | None = None
    pdf_url: str | None = None
    attempted_urls: list[str] = []
    file_path: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    mime_type: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class PdfCandidate:
    url: str
    source: str
    source_url: str | None = None


class LandingPageParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        values = {key.lower(): value for key, value in attrs if value is not None}
        if tag_name == "meta":
            name = (values.get("name") or values.get("property") or "").lower()
            if name not in {"citation_pdf_url", "fulltext_pdf_url"}:
                return
            content = values.get("content")
            if content:
                self.urls.append(urljoin(self.base_url, content))
            return

        if tag_name not in {"a", "link"}:
            return
        href = values.get("href")
        if not href:
            return
        href_lower = href.lower()
        link_type = (values.get("type") or "").lower()
        if (
            "pdf" in link_type
            or values.get("data-article-pdf") == "true"
            or href_lower.endswith(".pdf")
            or "/pdf" in urlparse(href_lower).path
        ):
            self.urls.append(urljoin(self.base_url, href))


class DownloadHttpClient:
    """HTTP helper for landing pages and binary downloads."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.json_client = HttpClient(settings)
        accept = (
            "text/html,application/pdf,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        )
        self.default_headers = {
            **self.json_client.default_headers,
            "Accept": accept,
        }

    def get_json(self, url: str, params: dict | None = None) -> dict:
        return self.json_client.get_json(url, params=params)

    def get_text(self, url: str) -> tuple[str, str | None]:
        with self._client() as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text, response.headers.get("content-type")

    def get_bytes(self, url: str) -> tuple[bytes, str | None]:
        with self._client() as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content, response.headers.get("content-type")

    def _client(self) -> httpx.Client:
        client_kwargs = {
            "timeout": self.settings.http_timeout_seconds,
            "trust_env": False,
            "follow_redirects": True,
            "headers": self.default_headers,
        }
        if self.settings.proxy_url:
            client_kwargs["proxy"] = self.settings.proxy_url
        return httpx.Client(**client_kwargs)


class DownloadService:
    """Find and download open-access PDFs for saved papers."""

    def __init__(self, settings: Settings, http_client: object | None = None) -> None:
        self.settings = settings
        self.http_client = http_client or DownloadHttpClient(settings)
        self.file_service = FileService(settings)

    def download_paper(
        self,
        paper_id: int,
        *,
        force: bool = False,
        output_dir: Path | None = None,
    ) -> DownloadResult:
        init_database(self.settings)
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            paper = session.get(Paper, paper_id)
            if not paper:
                raise LitSearchValidationError(f"Paper not found: {paper_id}")

            existing = self._latest_success(session, paper_id)
            if existing and existing.file_path and Path(existing.file_path).is_file() and not force:
                return self._result(existing)

            started_at = datetime.now(UTC)
            candidates = self._candidates(session, paper)
            if not candidates:
                download = self._new_download(
                    paper_id=paper_id,
                    status=DownloadStatus.skipped,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                    error="No open-access PDF URL found",
                )
                session.add(download)
                session.commit()
                session.refresh(download)
                return self._result(download)

            attempted: list[str] = []
            last_error = None
            for candidate in candidates:
                if candidate.url in attempted:
                    continue
                attempted.append(candidate.url)
                try:
                    content, mime_type = self.http_client.get_bytes(candidate.url)
                    self._validate_pdf(content, mime_type)
                except (httpx.HTTPError, ConnectorError, LitSearchValidationError) as exc:
                    last_error = str(exc)
                    continue

                digest = hashlib.sha256(content).hexdigest()
                metadata = {
                    "paper_id": paper_id,
                    "title": paper.title,
                    "doi": paper.doi,
                    "publication_year": paper.publication_year,
                    "source": candidate.source,
                    "source_url": candidate.source_url,
                    "pdf_url": candidate.url,
                    "sha256": digest,
                    "size_bytes": len(content),
                    "mime_type": mime_type,
                    "downloaded_at": datetime.now(UTC).isoformat(),
                }
                file_path = self.file_service.write_paper_files(
                    paper,
                    content,
                    metadata,
                    output_dir=output_dir,
                )
                download = self._new_download(
                    paper_id=paper_id,
                    status=DownloadStatus.downloaded,
                    source=candidate.source,
                    source_url=candidate.source_url,
                    pdf_url=candidate.url,
                    attempted_urls=attempted,
                    file_path=str(file_path.resolve()),
                    sha256=digest,
                    size_bytes=len(content),
                    mime_type=mime_type,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                )
                session.add(download)
                session.commit()
                session.refresh(download)
                return self._result(download)

            download = self._new_download(
                paper_id=paper_id,
                status=DownloadStatus.failed,
                attempted_urls=attempted,
                error=last_error or "All candidate PDF downloads failed",
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
            session.add(download)
            session.commit()
            session.refresh(download)
            return self._result(download)

    def list_downloads(self, limit: int = 50) -> list[DownloadResult]:
        init_database(self.settings)
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            downloads = session.exec(
                select(Download).order_by(Download.id.desc()).limit(limit)
            ).all()
            return [self._result(download) for download in downloads]

    def get_download(self, download_id: int) -> DownloadResult | None:
        init_database(self.settings)
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            download = session.get(Download, download_id)
            return self._result(download) if download else None

    def _candidates(self, session: Session, paper: Paper) -> list[PdfCandidate]:
        paper_sources = session.exec(
            select(PaperSource).where(PaperSource.paper_id == paper.id)
        ).all()
        candidates: list[PdfCandidate] = []
        for source in paper_sources:
            for url in self._raw_pdf_urls(source.raw_json):
                candidates.append(
                    PdfCandidate(url=url, source=source.source, source_url=source.source_url)
                )
        for source in paper_sources:
            if source.source_url:
                for url in self._landing_pdf_urls(source.source_url):
                    candidates.append(
                        PdfCandidate(url=url, source=source.source, source_url=source.source_url)
                    )
        if paper.doi:
            url = self._unpaywall_pdf_url(paper.doi)
            if url:
                candidates.append(PdfCandidate(url=url, source="unpaywall"))
            candidates.extend(self._openalex_pdf_candidates(paper.doi))

        seen: set[str] = set()
        unique = []
        for candidate in candidates:
            if candidate.url and candidate.url not in seen:
                seen.add(candidate.url)
                unique.append(candidate)
        return unique

    def _openalex_pdf_candidates(self, doi: str) -> list[PdfCandidate]:
        normalized = normalize_doi(doi)
        if not normalized:
            return []
        url = OPENALEX_DOI_URL_TEMPLATE.format(
            doi=quote(f"https://doi.org/{normalized}", safe="")
        )
        params = {}
        email = self.settings.source_email("openalex")
        if email:
            params["mailto"] = email
        try:
            payload = self.http_client.get_json(url, params=params or None)
        except (httpx.HTTPError, ConnectorError, KeyError):
            return []

        source_url = payload.get("id") if isinstance(payload.get("id"), str) else None
        candidates: list[PdfCandidate] = []
        for location in self._openalex_locations(payload):
            pdf_url = location.get("pdf_url")
            if isinstance(pdf_url, str) and pdf_url:
                candidates.append(
                    PdfCandidate(
                        url=pdf_url,
                        source="openalex",
                        source_url=source_url,
                    )
                )
        return candidates

    def _openalex_locations(self, payload: dict) -> list[dict]:
        locations: list[dict] = []
        for key in ("primary_location", "best_oa_location"):
            value = payload.get(key)
            if isinstance(value, dict):
                locations.append(value)
        for value in payload.get("locations") or []:
            if isinstance(value, dict):
                locations.append(value)
        return locations

    def _raw_pdf_urls(self, raw_json: str | None) -> list[str]:
        if not raw_json:
            return []
        try:
            raw = json.loads(raw_json)
        except ValueError:
            return []
        urls: list[str] = []

        def visit(value: object) -> None:
            if isinstance(value, dict):
                content_type = str(
                    value.get("content-type") or value.get("content_type") or ""
                ).lower()
                if content_type == "application/pdf" and isinstance(value.get("URL"), str):
                    urls.append(value["URL"])
                for key, item in value.items():
                    if key in PDF_KEYS and isinstance(item, str):
                        urls.append(item)
                    else:
                        visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        visit(raw)
        return urls

    def _landing_pdf_urls(self, source_url: str) -> list[str]:
        try:
            text, _mime_type = self.http_client.get_text(source_url)
        except (httpx.HTTPError, ConnectorError):
            return []
        parser = LandingPageParser(source_url)
        parser.feed(text)
        if parser.urls:
            return parser.urls
        # Tiny fallback for malformed pages that still expose standard meta names.
        pattern = re.compile(
            r"<meta[^>]+(?:citation_pdf_url|fulltext_pdf_url)[^>]+content=[\"']([^\"']+)",
            re.IGNORECASE,
        )
        return [urljoin(source_url, match) for match in pattern.findall(text)]

    def _unpaywall_pdf_url(self, doi: str) -> str | None:
        email = self.settings.source_email("unpaywall")
        if not email:
            return None
        url = UNPAYWALL_URL_TEMPLATE.format(doi=quote(doi, safe=""))
        try:
            payload = self.http_client.get_json(url, params={"email": email})
        except (httpx.HTTPError, ConnectorError):
            return None
        best_location = payload.get("best_oa_location") or {}
        if isinstance(best_location, dict) and best_location.get("url_for_pdf"):
            return str(best_location["url_for_pdf"])
        return None

    def _validate_pdf(self, content: bytes, mime_type: str | None) -> None:
        if "pdf" in (mime_type or "").lower() or content.startswith(b"%PDF"):
            return
        raise LitSearchValidationError("HTTP response was not a PDF")

    def _latest_success(self, session: Session, paper_id: int) -> Download | None:
        return session.exec(
            select(Download)
            .where(Download.paper_id == paper_id, Download.status == DownloadStatus.downloaded)
            .order_by(Download.id.desc())
        ).first()

    def _new_download(self, **kwargs) -> Download:
        attempted_urls = kwargs.pop("attempted_urls", None)
        if attempted_urls is not None:
            kwargs["attempted_urls"] = json.dumps(attempted_urls, ensure_ascii=False)
        return Download(**kwargs)

    def _result(self, download: Download) -> DownloadResult:
        attempted_urls = json.loads(download.attempted_urls) if download.attempted_urls else []
        return DownloadResult(
            id=download.id or 0,
            paper_id=download.paper_id,
            status=(
                download.status.value
                if hasattr(download.status, "value")
                else str(download.status)
            ),
            source=download.source,
            source_url=download.source_url,
            pdf_url=download.pdf_url,
            attempted_urls=attempted_urls,
            file_path=download.file_path,
            sha256=download.sha256,
            size_bytes=download.size_bytes,
            mime_type=download.mime_type,
            error=download.error,
        )
