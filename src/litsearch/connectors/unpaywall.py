"""Unpaywall DOI lookup connector."""

from __future__ import annotations

from urllib.parse import quote

from litsearch.config import Settings
from litsearch.connectors.base import SourcePaper
from litsearch.connectors.http import HttpClient

UNPAYWALL_URL_TEMPLATE = "https://api.unpaywall.org/v2/{doi}"


class UnpaywallConnector:
    def __init__(self, settings: Settings, http_client: HttpClient | None = None):
        self.settings = settings
        self.http_client = http_client or HttpClient(settings)

    def lookup_by_doi(self, doi: str) -> SourcePaper | None:
        email = self.settings.source_email("unpaywall")
        if not email:
            return None
        url = UNPAYWALL_URL_TEMPLATE.format(doi=quote(doi, safe=""))
        payload = self.http_client.get_json(url, params={"email": email})
        if not payload.get("doi") and not payload.get("title"):
            return None
        best_location = payload.get("best_oa_location") or {}
        return SourcePaper(
            source="unpaywall",
            source_paper_id=payload.get("doi"),
            title=payload.get("title") or doi,
            doi=payload.get("doi"),
            publication_year=payload.get("year"),
            authors=[
                " ".join(part for part in (author.get("given"), author.get("family")) if part)
                for author in payload.get("z_authors", [])
                if author.get("given") or author.get("family")
            ],
            venue_name=payload.get("journal_name"),
            pdf_url=best_location.get("url_for_pdf"),
            is_open_access=payload.get("is_oa"),
            raw=payload,
        )
