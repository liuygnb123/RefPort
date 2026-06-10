"""Normalization helpers for metadata matching."""

from __future__ import annotations

import re

HTML_TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
YEAR_RE = re.compile(r"^(\d{4})")


def _collapse(value: str) -> str:
    return SPACE_RE.sub(" ", value).strip()


def normalize_doi(value: str | None) -> str | None:
    """Normalize DOI strings and DOI URLs for matching."""

    if not value:
        return None
    doi = value.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi.removeprefix(prefix)
            break
    doi = doi.strip().strip(".,;")
    return doi or None


def normalize_title(value: str | None) -> str | None:
    """Normalize titles conservatively for exact dedupe."""

    if not value:
        return None
    title = HTML_TAG_RE.sub(" ", value)
    title = _collapse(title).lower()
    return title or None


def normalize_name(value: str | None) -> str | None:
    """Normalize human or venue names."""

    if not value:
        return None
    name = _collapse(value).lower()
    return name or None


def extract_year(value: str | None) -> int | None:
    """Extract a leading four-digit year from a date string."""

    if not value:
        return None
    match = YEAR_RE.match(value.strip())
    if not match:
        return None
    return int(match.group(1))
