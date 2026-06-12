"""Mutation service for library items and tags."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import delete
from sqlmodel import Session, select

from litsearch.config import Settings
from litsearch.db.session import create_db_engine, init_database
from litsearch.exceptions import LitSearchValidationError
from litsearch.models import LibraryItem, LibraryStatus, Paper, PaperTag, Tag
from litsearch.normalization import normalize_name


class LibraryItemSummary(BaseModel):
    paper_id: int
    status: str
    favorite: bool
    rating: int | None
    notes: str | None


class TagSummary(BaseModel):
    id: int
    name: str
    paper_count: int


class LibraryService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def add_or_update_library_item(
        self,
        paper_id: int,
        status: LibraryStatus = LibraryStatus.unread,
        favorite: bool = False,
        rating: int | None = None,
        notes: str | None = None,
    ) -> LibraryItemSummary:
        self._validate_rating(rating)
        init_database(self.settings)
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            self._require_paper(session, paper_id)
            item = session.exec(
                select(LibraryItem).where(LibraryItem.paper_id == paper_id)
            ).first()
            if not item:
                item = LibraryItem(paper_id=paper_id)
            item.status = status
            item.favorite = favorite
            item.rating = rating
            item.notes = notes
            item.updated_at = datetime.now(UTC)
            session.add(item)
            session.commit()
            session.refresh(item)
            return self._summary(item)

    def update_library_item(
        self,
        paper_id: int,
        status: LibraryStatus | None = None,
        favorite: bool | None = None,
        rating: int | None = None,
        notes: str | None = None,
        rating_set: bool = False,
        notes_set: bool = False,
    ) -> LibraryItemSummary:
        if rating_set:
            self._validate_rating(rating)
        init_database(self.settings)
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            self._require_paper(session, paper_id)
            item = session.exec(
                select(LibraryItem).where(LibraryItem.paper_id == paper_id)
            ).first()
            if not item:
                item = LibraryItem(paper_id=paper_id)
            if status is not None:
                item.status = status
            if favorite is not None:
                item.favorite = favorite
            if rating_set:
                item.rating = rating
            if notes_set:
                item.notes = notes
            item.updated_at = datetime.now(UTC)
            session.add(item)
            session.commit()
            session.refresh(item)
            return self._summary(item)

    def remove_library_item(self, paper_id: int) -> bool:
        init_database(self.settings)
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            self._require_paper(session, paper_id)
            item = session.exec(
                select(LibraryItem).where(LibraryItem.paper_id == paper_id)
            ).first()
            if not item:
                return False
            session.delete(item)
            session.commit()
            return True

    def list_tags(self) -> list[TagSummary]:
        init_database(self.settings)
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            tags = session.exec(select(Tag).order_by(Tag.name_normalized)).all()
            return [self._tag_summary(session, tag) for tag in tags]

    def add_tag(self, name: str) -> TagSummary:
        normalized = self._normalized_tag(name)
        init_database(self.settings)
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            tag = session.exec(select(Tag).where(Tag.name_normalized == normalized)).first()
            if not tag:
                tag = Tag(name=name.strip(), name_normalized=normalized)
                session.add(tag)
                session.commit()
                session.refresh(tag)
            return self._tag_summary(session, tag)

    def remove_tag(self, name: str) -> bool:
        normalized = self._normalized_tag(name)
        init_database(self.settings)
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            tag = session.exec(select(Tag).where(Tag.name_normalized == normalized)).first()
            if not tag:
                return False
            session.exec(delete(PaperTag).where(PaperTag.tag_id == tag.id))
            session.delete(tag)
            session.commit()
            return True

    def tag_paper(self, paper_id: int, tag_name: str) -> TagSummary:
        normalized = self._normalized_tag(tag_name)
        init_database(self.settings)
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            self._require_paper(session, paper_id)
            tag = session.exec(select(Tag).where(Tag.name_normalized == normalized)).first()
            if not tag:
                tag = Tag(name=tag_name.strip(), name_normalized=normalized)
                session.add(tag)
                session.flush()
            link = session.exec(
                select(PaperTag).where(PaperTag.paper_id == paper_id, PaperTag.tag_id == tag.id)
            ).first()
            if not link:
                session.add(PaperTag(paper_id=paper_id, tag_id=tag.id))
            session.commit()
            session.refresh(tag)
            return self._tag_summary(session, tag)

    def untag_paper(self, paper_id: int, tag_name: str) -> bool:
        normalized = self._normalized_tag(tag_name)
        init_database(self.settings)
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            self._require_paper(session, paper_id)
            tag = session.exec(select(Tag).where(Tag.name_normalized == normalized)).first()
            if not tag:
                return False
            link = session.exec(
                select(PaperTag).where(PaperTag.paper_id == paper_id, PaperTag.tag_id == tag.id)
            ).first()
            if not link:
                return False
            session.delete(link)
            session.commit()
            return True

    def _require_paper(self, session: Session, paper_id: int) -> Paper:
        paper = session.get(Paper, paper_id)
        if not paper:
            raise LitSearchValidationError(f"Paper not found: {paper_id}")
        return paper

    def _normalized_tag(self, name: str) -> str:
        normalized = normalize_name(name)
        if not normalized:
            raise LitSearchValidationError("tag name must not be empty")
        return normalized

    def _validate_rating(self, rating: int | None) -> None:
        if rating is not None and not 1 <= rating <= 5:
            raise LitSearchValidationError("rating must be between 1 and 5")

    def _summary(self, item: LibraryItem) -> LibraryItemSummary:
        return LibraryItemSummary(
            paper_id=item.paper_id,
            status=item.status.value if hasattr(item.status, "value") else str(item.status),
            favorite=item.favorite,
            rating=item.rating,
            notes=item.notes,
        )

    def _tag_summary(self, session: Session, tag: Tag) -> TagSummary:
        count = len(session.exec(select(PaperTag).where(PaperTag.tag_id == tag.id)).all())
        return TagSummary(id=tag.id, name=tag.name, paper_count=count)
