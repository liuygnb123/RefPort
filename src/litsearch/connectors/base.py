"""Shared connector metadata types."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SourceDefinition(BaseModel):
    id: str
    display_name: str
    requires: list[str]
    capabilities: list[str]


class SourceStatus(SourceDefinition):
    configured: bool


class SearchRequest(BaseModel):
    query: str
    limit: int = 10


class SourcePaper(BaseModel):
    source: str
    source_paper_id: str | None = None
    title: str
    abstract: str | None = None
    doi: str | None = None
    publication_year: int | None = None
    publication_date: str | None = None
    authors: list[str] = Field(default_factory=list)
    venue_name: str | None = None
    source_url: str | None = None
    pdf_url: str | None = None
    is_open_access: bool | None = None
    citation_count: int | None = None
    raw: dict = Field(default_factory=dict)
