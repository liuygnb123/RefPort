"""Shared model fields."""

from datetime import UTC, datetime

from sqlmodel import Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
