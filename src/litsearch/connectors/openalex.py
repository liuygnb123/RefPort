"""OpenAlex metadata connector."""

from __future__ import annotations

from litsearch.config import Settings
from litsearch.connectors.base import SearchRequest, SourcePaper
from litsearch.connectors.http import HttpClient

OPENALEX_WORKS_URL = "https://api.openalex.org/works"


def _abstract_from_inverted_index(value: dict | None) -> str | None:
    if not value:
        return None
    positions: list[tuple[int, str]] = []
    for word, indexes in value.items():
        for index in indexes:
            positions.append((int(index), word))
    if not positions:
        return None
    return " ".join(word for _, word in sorted(positions))


class OpenAlexConnector:
    def __init__(self, settings: Settings, http_client: HttpClient | None = None):
        self.settings = settings
        self.http_client = http_client or HttpClient(settings)

    def search(self, request: SearchRequest) -> list[SourcePaper]:
        params = {
            "search": request.query,
            "per-page": request.limit,
        }
        email = self.settings.source_email("openalex")
        if email:
            params["mailto"] = email
        payload = self.http_client.get_json(OPENALEX_WORKS_URL, params=params)
        return [self._parse_work(item) for item in payload.get("results", []) if item.get("title")]

    def _parse_work(self, item: dict) -> SourcePaper:
        primary_location = item.get("primary_location") or {}
        source = primary_location.get("source") or {}
        open_access = item.get("open_access") or {}
        return SourcePaper(
            source="openalex",
            source_paper_id=item.get("id"),
            title=item["title"],
            abstract=_abstract_from_inverted_index(item.get("abstract_inverted_index")),
            doi=item.get("doi"),
            publication_year=item.get("publication_year"),
            authors=[
                authorship["author"]["display_name"]
                for authorship in item.get("authorships", [])
                if (authorship.get("author") or {}).get("display_name")
            ],
            venue_name=source.get("display_name"),
            source_url=item.get("id"),
            pdf_url=primary_location.get("pdf_url"),
            is_open_access=open_access.get("is_oa"),
            citation_count=item.get("cited_by_count"),
            raw=item,
        )
