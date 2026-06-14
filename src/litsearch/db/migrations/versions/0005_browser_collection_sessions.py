"""browser collection sessions

Revision ID: 0005_browser_collection_sessions
Revises: 0004_download_files
Create Date: 2026-06-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_browser_collection_sessions"
down_revision: str | None = "0004_download_files"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tables() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return set(inspector.get_table_names())


def upgrade() -> None:
    existing = _tables()
    if "browser_sessions" not in existing:
        op.create_table(
            "browser_sessions",
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("platform", sa.String(), nullable=False),
            sa.Column("entry_url", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("login_state", sa.String(), nullable=False),
            sa.Column("error", sa.String(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_browser_sessions_platform", "browser_sessions", ["platform"])
        op.create_index("ix_browser_sessions_status", "browser_sessions", ["status"])
        op.create_index("ix_browser_sessions_login_state", "browser_sessions", ["login_state"])

    existing = _tables()
    if "browser_snapshots" not in existing:
        op.create_table(
            "browser_snapshots",
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("session_id", sa.Integer(), nullable=False),
            sa.Column("url", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("html_path", sa.String(), nullable=False),
            sa.Column("screenshot_path", sa.String(), nullable=True),
            sa.Column("login_state", sa.String(), nullable=False),
            sa.Column("blocked_reason", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(["session_id"], ["browser_sessions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_browser_snapshots_session_id", "browser_snapshots", ["session_id"])
        op.create_index("ix_browser_snapshots_login_state", "browser_snapshots", ["login_state"])

    existing = _tables()
    if "browser_imports" not in existing:
        op.create_table(
            "browser_imports",
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("session_id", sa.Integer(), nullable=False),
            sa.Column("snapshot_id", sa.Integer(), nullable=True),
            sa.Column("paper_id", sa.Integer(), nullable=False),
            sa.Column("action", sa.String(), nullable=False),
            sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
            sa.ForeignKeyConstraint(["session_id"], ["browser_sessions.id"]),
            sa.ForeignKeyConstraint(["snapshot_id"], ["browser_snapshots.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_browser_imports_session_id", "browser_imports", ["session_id"])
        op.create_index("ix_browser_imports_snapshot_id", "browser_imports", ["snapshot_id"])
        op.create_index("ix_browser_imports_paper_id", "browser_imports", ["paper_id"])


def downgrade() -> None:
    existing = _tables()
    if "browser_imports" in existing:
        op.drop_index("ix_browser_imports_paper_id", table_name="browser_imports")
        op.drop_index("ix_browser_imports_snapshot_id", table_name="browser_imports")
        op.drop_index("ix_browser_imports_session_id", table_name="browser_imports")
        op.drop_table("browser_imports")
    existing = _tables()
    if "browser_snapshots" in existing:
        op.drop_index("ix_browser_snapshots_login_state", table_name="browser_snapshots")
        op.drop_index("ix_browser_snapshots_session_id", table_name="browser_snapshots")
        op.drop_table("browser_snapshots")
    existing = _tables()
    if "browser_sessions" in existing:
        op.drop_index("ix_browser_sessions_login_state", table_name="browser_sessions")
        op.drop_index("ix_browser_sessions_status", table_name="browser_sessions")
        op.drop_index("ix_browser_sessions_platform", table_name="browser_sessions")
        op.drop_table("browser_sessions")
