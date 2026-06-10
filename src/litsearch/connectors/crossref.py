"""Crossref metadata connector."""

from __future__ import annotations

from litsearch.config import Settings
from litsearch.connectors.base import SearchRequest, SourcePaper
from litsearch.connectors.http import HttpClient
from litsearch.normalization import normalize_title

CROSSREF_WORKS_URL = "https://api.crossref.org/works"


def _first(values: list | None) -> str | None:
    if not values:
        return None
    value = values[0]
    return str(value) if value is not None else None


def _year_from_parts(value: dict | None) -> int | None:
    parts = (value or {}).get("date-parts") or []
    if not parts or not parts[0]:
        return None
    return int(parts[0][0])


class CrossrefConnector:
    def __init__(self, settings: Settings, http_client: HttpClient | None = None):
        self.settings = settings
        self.http_client = http_client or HttpClient(settings)

    def search(self, request: SearchRequest) -> list[SourcePaper]:
        params = {
            "query": request.query,
            "rows": request.limit,
        }
        email = self.settings.source_email("crossref")
        if email:
            params["mailto"] = email
        payload = self.http_client.get_json(CROSSREF_WORKS_URL, params=params)
        items = (payload.get("message") or {}).get("items", [])
        return [self._parse_work(item) for item in items if _first(item.get("title"))]

    def _parse_work(self, item: dict) -> SourcePaper:
        title = _first(item.get("title")) or ""
        year = (
            _year_from_parts(item.get("published-print"))
            or _year_from_parts(item.get("published-online"))
            or _year_from_parts(item.get("published"))
        )
        return SourcePaper(
            source="crossref",
            source_paper_id=item.get("DOI"),
            title=title,
            abstract=normalize_title(item.get("abstract")),
            doi=item.get("DOI"),
            publication_year=year,
            authors=[
                " ".join(part for part in (author.get("given"), author.get("family")) if part)
                for author in item.get("author", [])
                if author.get("given") or author.get("family")
            ],
            venue_name=_first(item.get("container-title")),
            source_url=item.get("URL"),
            citation_count=item.get("is-referenced-by-count"),
            raw=item,
        )
