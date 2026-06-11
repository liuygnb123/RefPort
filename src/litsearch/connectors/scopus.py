"""Scopus Search API metadata connector."""

from __future__ import annotations

from typing import Any

from litsearch.config import Settings
from litsearch.connectors.base import SearchRequest, SourcePaper
from litsearch.connectors.http import HttpClient
from litsearch.exceptions import SourceNotConfiguredError

SCOPUS_SEARCH_URL = "https://api.elsevier.com/content/search/scopus"


def _year_from_date(value: str | None) -> int | None:
    if not value or len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _authors_from_entry(entry: dict) -> list[str]:
    authors = entry.get("author")
    if isinstance(authors, list):
        names = [
            author.get("authname") or author.get("ce:indexed-name") or author.get("surname")
            for author in authors
            if isinstance(author, dict)
        ]
        return [name for name in names if name]
    creator = entry.get("dc:creator")
    return [creator] if creator else []


def _source_url_from_links(entry: dict) -> str | None:
    links = entry.get("link")
    if not isinstance(links, list):
        return None
    for link in links:
        if isinstance(link, dict) and link.get("@ref") == "scopus":
            return link.get("@href")
    return None


class ScopusConnector:
    """Search Scopus metadata through Elsevier's official API."""

    def __init__(self, settings: Settings, http_client: HttpClient | None = None):
        self.settings = settings
        self.http_client = http_client or HttpClient(settings)

    def search(self, request: SearchRequest) -> list[SourcePaper]:
        if not self.settings.scopus_api_key:
            raise SourceNotConfiguredError("Scopus API key is not configured")

        params = {
            "query": request.query,
            # The Scopus Search API accepts at most 25 results per request in this phase.
            "count": min(request.limit, 25),
        }
        headers = {
            "Accept": "application/json",
            "X-ELS-APIKey": self.settings.scopus_api_key,
        }
        if self.settings.scopus_inst_token:
            headers["X-ELS-Insttoken"] = self.settings.scopus_inst_token

        payload = self.http_client.get_json(SCOPUS_SEARCH_URL, params=params, headers=headers)
        entries = (payload.get("search-results") or {}).get("entry") or []
        return [
            self._parse_entry(entry)
            for entry in entries
            if isinstance(entry, dict) and entry.get("dc:title")
        ]

    def _parse_entry(self, entry: dict) -> SourcePaper:
        cover_date = entry.get("prism:coverDate")
        open_access = _as_bool(entry.get("openaccessFlag"))
        if open_access is None:
            open_access = _as_bool(entry.get("openaccess"))

        return SourcePaper(
            source="scopus",
            source_paper_id=entry.get("eid") or entry.get("dc:identifier"),
            title=entry["dc:title"],
            abstract=entry.get("dc:description") or entry.get("prism:teaser"),
            doi=entry.get("prism:doi"),
            publication_year=_year_from_date(cover_date),
            publication_date=cover_date,
            authors=_authors_from_entry(entry),
            venue_name=entry.get("prism:publicationName") or entry.get("prism:issueName"),
            source_url=_source_url_from_links(entry),
            pdf_url=None,
            is_open_access=open_access,
            citation_count=_as_int(entry.get("citedby-count")),
            raw=entry,
        )
