"""Persistence helpers for normalized source metadata."""

from __future__ import annotations

import json

from sqlmodel import Session, select

from litsearch.connectors.base import SourcePaper
from litsearch.models import Author, Paper, PaperAuthor, PaperSource, Venue
from litsearch.normalization import normalize_doi, normalize_name, normalize_title


def _first_filled(existing: str | None, incoming: str | None) -> str | None:
    return existing or incoming


def _get_or_create_venue(session: Session, name: str | None) -> Venue | None:
    normalized = normalize_name(name)
    if not name or not normalized:
        return None
    venue = session.exec(select(Venue).where(Venue.name_normalized == normalized)).first()
    if venue:
        return venue
    venue = Venue(name=name, name_normalized=normalized)
    session.add(venue)
    session.flush()
    return venue


def _get_or_create_author(session: Session, name: str) -> Author:
    normalized = normalize_name(name)
    author = None
    if normalized:
        author = session.exec(select(Author).where(Author.name_normalized == normalized)).first()
    if author:
        return author
    author = Author(name=name, name_normalized=normalized)
    session.add(author)
    session.flush()
    return author


def _find_paper(session: Session, source_paper: SourcePaper) -> Paper | None:
    doi = normalize_doi(source_paper.doi)
    if doi:
        return session.exec(select(Paper).where(Paper.doi_normalized == doi)).first()
    title = normalize_title(source_paper.title)
    if title and source_paper.publication_year:
        return session.exec(
            select(Paper).where(
                Paper.title_normalized == title,
                Paper.publication_year == source_paper.publication_year,
            )
        ).first()
    return None


def _sync_authors(session: Session, paper: Paper, authors: list[str]) -> None:
    if paper.id is None:
        session.flush()
    existing_links = session.exec(select(PaperAuthor).where(PaperAuthor.paper_id == paper.id)).all()
    if existing_links:
        return
    seen: set[str] = set()
    order = 1
    for name in authors:
        normalized = normalize_name(name)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        author = _get_or_create_author(session, name)
        session.add(PaperAuthor(paper_id=paper.id, author_id=author.id, author_order=order))
        order += 1


def _sync_source(session: Session, paper: Paper, source_paper: SourcePaper) -> None:
    if paper.id is None:
        session.flush()
    query = select(PaperSource).where(
        PaperSource.paper_id == paper.id,
        PaperSource.source == source_paper.source,
    )
    if source_paper.source_paper_id:
        query = query.where(PaperSource.source_paper_id == source_paper.source_paper_id)
    else:
        query = query.where(PaperSource.source_url == source_paper.source_url)
    paper_source = session.exec(query).first()
    raw_json = json.dumps(source_paper.raw, ensure_ascii=False, sort_keys=True)
    if paper_source:
        paper_source.source_url = _first_filled(paper_source.source_url, source_paper.source_url)
        paper_source.raw_json = _first_filled(paper_source.raw_json, raw_json)
        session.add(paper_source)
        return
    session.add(
        PaperSource(
            paper_id=paper.id,
            source=source_paper.source,
            source_paper_id=source_paper.source_paper_id,
            source_url=source_paper.source_url,
            raw_json=raw_json,
        )
    )


def upsert_source_paper(session: Session, source_paper: SourcePaper) -> Paper:
    """Create or update a Paper from source metadata."""

    title_normalized = normalize_title(source_paper.title)
    doi_normalized = normalize_doi(source_paper.doi)
    paper = _find_paper(session, source_paper)
    venue = _get_or_create_venue(session, source_paper.venue_name)

    if not paper:
        paper = Paper(
            title=source_paper.title,
            title_normalized=title_normalized,
            doi=source_paper.doi,
            doi_normalized=doi_normalized,
            publication_year=source_paper.publication_year,
            abstract=source_paper.abstract,
            venue_id=venue.id if venue else None,
        )
        session.add(paper)
        session.flush()
    else:
        paper.title_normalized = _first_filled(paper.title_normalized, title_normalized)
        paper.doi = _first_filled(paper.doi, source_paper.doi)
        paper.doi_normalized = _first_filled(paper.doi_normalized, doi_normalized)
        paper.publication_year = paper.publication_year or source_paper.publication_year
        paper.abstract = _first_filled(paper.abstract, source_paper.abstract)
        paper.venue_id = paper.venue_id or (venue.id if venue else None)
        session.add(paper)

    _sync_authors(session, paper, source_paper.authors)
    _sync_source(session, paper, source_paper)
    session.flush()
    return paper
