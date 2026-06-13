"""download files

Revision ID: 0004_download_files
Revises: 0003_library_tags_exports
Create Date: 2026-06-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_download_files"
down_revision: str | None = "0003_library_tags_exports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns("downloads")}


def _add_column_if_missing(existing: set[str], column: sa.Column) -> None:
    if column.name not in existing:
        op.add_column("downloads", column)


def upgrade() -> None:
    existing = _columns()
    _add_column_if_missing(existing, sa.Column("source", sa.String(), nullable=True))
    _add_column_if_missing(existing, sa.Column("source_url", sa.String(), nullable=True))
    _add_column_if_missing(existing, sa.Column("pdf_url", sa.String(), nullable=True))
    _add_column_if_missing(existing, sa.Column("attempted_urls", sa.String(), nullable=True))
    _add_column_if_missing(existing, sa.Column("size_bytes", sa.Integer(), nullable=True))
    _add_column_if_missing(existing, sa.Column("mime_type", sa.String(), nullable=True))
    _add_column_if_missing(existing, sa.Column("started_at", sa.DateTime(), nullable=True))
    _add_column_if_missing(existing, sa.Column("finished_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    existing = _columns()
    for name in (
        "finished_at",
        "started_at",
        "mime_type",
        "size_bytes",
        "attempted_urls",
        "pdf_url",
        "source_url",
        "source",
    ):
        if name in existing:
            op.drop_column("downloads", name)
