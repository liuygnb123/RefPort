"""Venue model."""

from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from litsearch.models._mixins import TimestampMixin

if TYPE_CHECKING:
    from litsearch.models.paper import Paper


class Venue(TimestampMixin, SQLModel, table=True):
    __tablename__ = "venues"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    name_normalized: str | None = Field(default=None, index=True)
    venue_type: str | None = Field(default=None)
    issn: str | None = Field(default=None)
    publisher: str | None = Field(default=None)

    papers: list["Paper"] = Relationship(back_populates="venue")
