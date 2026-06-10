"""Paper identity helpers."""

from __future__ import annotations

from litsearch.connectors.base import SourcePaper
from litsearch.normalization import normalize_doi, normalize_title


def paper_identity(source_paper: SourcePaper) -> tuple[str, str] | None:
    doi = normalize_doi(source_paper.doi)
    if doi:
        return ("doi", doi)
    title = normalize_title(source_paper.title)
    if title and source_paper.publication_year:
        return ("title_year", f"{title}|{source_paper.publication_year}")
    return None
