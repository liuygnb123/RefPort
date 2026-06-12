"""Web of Science Starter API connector."""

from __future__ import annotations

from typing import Any

from litsearch.config import Settings
from litsearch.connectors.base import SearchRequest, SourcePaper
from litsearch.connectors.http import HttpClient
from litsearch.exceptions import SourceNotConfiguredError

WOS_DOCUMENTS_URL = "https://api.clarivate.com/apis/wos-starter/v1/documents"
WOS_QUERY_FIELDS = {
    "AI",
    "AU",
    "DO",
    "DT",
    "ED",
    "GP",
    "IS",
    "OG",
    "OO",
    "PMID",
    "PY",
    "SO",
    "SU",
    "TI",
    "TS",
    "UT",
}


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _year_from_date(value: str | None) -> int | None:
    if not value or len(value) < 4:
        return None
    return _as_int(value[:4])


def _first_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in value:
            text = _first_text(item)
            if text:
                return text
    if isinstance(value, dict):
        for key in ("value", "title", "text"):
            text = _first_text(value.get(key))
            if text:
                return text
    return None


def _doi(document: dict) -> str | None:
    identifiers = document.get("identifiers")
    if isinstance(identifiers, dict):
        doi = identifiers.get("doi")
        if doi:
            return doi
    return document.get("doi")


def _authors(document: dict) -> list[str]:
    names = document.get("names") or {}
    authors = names.get("authors") if isinstance(names, dict) else None
    if authors is None:
        authors = document.get("authors")
    if not isinstance(authors, list):
        return []
    values = [
        author.get("displayName") or author.get("fullName") or author.get("name")
        for author in authors
        if isinstance(author, dict)
    ]
    return [value for value in values if value]


def _citation_count(document: dict) -> int | None:
    citations = document.get("citations")
    if isinstance(citations, list):
        for citation in citations:
            if not isinstance(citation, dict):
                continue
            db = str(citation.get("db") or citation.get("database") or "").upper()
            if db in {"WOS", "WEB OF SCIENCE"}:
                return _as_int(citation.get("count") or citation.get("timesCited"))
    if isinstance(citations, dict):
        return _as_int(citations.get("count") or citations.get("timesCited"))
    return _as_int(document.get("timesCited"))


def _source_url(document: dict) -> str | None:
    links = document.get("links")
    if isinstance(links, dict):
        return links.get("record") or links.get("wos")
    return document.get("recordUrl") or document.get("wosUrl")


def _wos_query(query: str) -> str:
    """Return a WoS advanced-search query, preserving user-provided syntax."""

    stripped = query.strip()
    if any(stripped.upper().startswith(f"{field}=") for field in WOS_QUERY_FIELDS):
        return stripped
    escaped = stripped.replace('"', r"\"")
    return f'TS=("{escaped}")'


class WosConnector:
    """Search Web of Science Starter metadata through the official API."""

    def __init__(self, settings: Settings, http_client: HttpClient | None = None):
        self.settings = settings
        self.http_client = http_client or HttpClient(settings)

    def search(self, request: SearchRequest) -> list[SourcePaper]:
        if not self.settings.wos_api_key:
            raise SourceNotConfiguredError("Web of Science API key is not configured")

        payload = self.http_client.get_json(
            WOS_DOCUMENTS_URL,
            params={
                "db": "WOS",
                "q": _wos_query(request.query),
                "limit": min(request.limit, 50),
                "page": 1,
            },
            headers={
                "Accept": "application/json",
                "X-ApiKey": self.settings.wos_api_key,
            },
        )
        documents = payload.get("hits") or payload.get("documents") or []
        return [
            self._parse_document(document)
            for document in documents
            if isinstance(document, dict) and _first_text(document.get("title"))
        ]

    def _parse_document(self, document: dict) -> SourcePaper:
        source = document.get("source") or {}
        open_access = document.get("openAccess") or {}
        publication_date = document.get("publicationDate")
        publication_year = _as_int(source.get("publishYear")) or _year_from_date(publication_date)

        return SourcePaper(
            source="wos",
            source_paper_id=document.get("uid") or document.get("UT"),
            title=_first_text(document.get("title")) or "",
            abstract=_first_text(document.get("abstract")),
            doi=_doi(document),
            publication_year=publication_year,
            publication_date=publication_date,
            authors=_authors(document),
            venue_name=source.get("sourceTitle") or source.get("title"),
            source_url=_source_url(document),
            pdf_url=None,
            is_open_access=open_access.get("isOpenAccess")
            if isinstance(open_access, dict)
            else None,
            citation_count=_citation_count(document),
            raw=document,
        )
