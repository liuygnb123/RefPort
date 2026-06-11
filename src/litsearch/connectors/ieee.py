"""IEEE Xplore Metadata API connector."""

from __future__ import annotations

from typing import Any

from litsearch.config import Settings
from litsearch.connectors.base import SearchRequest, SourcePaper
from litsearch.connectors.http import HttpClient
from litsearch.exceptions import SourceNotConfiguredError

IEEE_SEARCH_URL = "https://ieeexploreapi.ieee.org/api/v1/search/articles"


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _year_from_date(value: str | None) -> int | None:
    if not value:
        return None
    for token in value.replace("/", "-").split("-"):
        year = _as_int(token)
        if year and 1000 <= year <= 9999:
            return year
    if len(value) >= 4:
        return _as_int(value[:4])
    return None


def _authors_from_article(article: dict) -> list[str]:
    authors = article.get("authors")
    if isinstance(authors, dict):
        authors = authors.get("authors")
    if not isinstance(authors, list):
        return []
    names = [
        author.get("full_name") or author.get("name")
        for author in authors
        if isinstance(author, dict)
    ]
    return [name for name in names if name]


def _source_url(article: dict) -> str | None:
    if article.get("html_url"):
        return article.get("html_url")
    if article.get("doi"):
        return f"https://doi.org/{article['doi']}"
    article_number = article.get("article_number")
    if article_number:
        return f"https://ieeexplore.ieee.org/document/{article_number}"
    return None


def _open_access(article: dict) -> bool | None:
    access_type = article.get("access_type")
    if not access_type:
        return None
    normalized = str(access_type).strip().upper()
    if normalized == "OPEN_ACCESS":
        return True
    if normalized == "LOCKED":
        return False
    return None


class IEEEConnector:
    """Search IEEE Xplore metadata through the official API."""

    def __init__(self, settings: Settings, http_client: HttpClient | None = None):
        self.settings = settings
        self.http_client = http_client or HttpClient(settings)

    def search(self, request: SearchRequest) -> list[SourcePaper]:
        if not self.settings.ieee_api_key:
            raise SourceNotConfiguredError("IEEE Xplore API key is not configured")

        payload = self.http_client.get_json(
            IEEE_SEARCH_URL,
            params={
                "querytext": request.query,
                "max_records": request.limit,
                "apikey": self.settings.ieee_api_key,
            },
        )
        articles = payload.get("articles") or []
        return [
            self._parse_article(article)
            for article in articles
            if isinstance(article, dict) and article.get("title")
        ]

    def _parse_article(self, article: dict) -> SourcePaper:
        publication_date = article.get("publication_date")
        publication_year = _as_int(article.get("publication_year")) or _year_from_date(
            publication_date
        )
        source_paper_id = article.get("article_number")

        return SourcePaper(
            source="ieee",
            source_paper_id=str(source_paper_id) if source_paper_id is not None else None,
            title=article["title"],
            abstract=article.get("abstract"),
            doi=article.get("doi"),
            publication_year=publication_year,
            publication_date=publication_date,
            authors=_authors_from_article(article),
            venue_name=article.get("publication_title"),
            source_url=_source_url(article),
            pdf_url=article.get("pdf_url"),
            is_open_access=_open_access(article),
            citation_count=_as_int(article.get("citing_paper_count")),
            raw=article,
        )
