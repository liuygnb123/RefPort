"""SQLModel table definitions."""

from litsearch.models.author import Author, PaperAuthor
from litsearch.models.download import Download, DownloadStatus
from litsearch.models.paper import Paper
from litsearch.models.search import SearchResultItem, SearchRun, SearchRunStatus
from litsearch.models.source import PaperSource
from litsearch.models.venue import Venue

__all__ = [
    "Author",
    "Download",
    "DownloadStatus",
    "Paper",
    "PaperAuthor",
    "PaperSource",
    "SearchRun",
    "SearchResultItem",
    "SearchRunStatus",
    "Venue",
]
