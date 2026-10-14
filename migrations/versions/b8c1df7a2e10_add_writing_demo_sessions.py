"""add local writing demo sessions and revisions

Revision ID: b8c1df7a2e10
Revises: da3577360b3f
Create Date: 2026-10-13

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8c1df7a2e10"
down_revision: str | None = "da3577360b3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "writing_demo_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("felhasznalo_nev", sa.String(length=64), nullable=False),
        sa.Column("feladat_id", sa.String(length=64), nullable=False),
        sa.Column("feladat_prompt", sa.Text(), nullable=False),
        sa.Column("guide_id", sa.String(length=128), nullable=False),
        sa.Column("guide_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("utc_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("utc_last_resumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_seconds", sa.Integer(), nullable=False),
        sa.Column("utc_submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_writing_demo_sessions_felhasznalo_nev",
        "writing_demo_sessions",
        ["felhasznalo_nev"],
        unique=False,
    )
    op.create_table(
        "writing_demo_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("draft_text", sa.Text(), nullable=False),
        sa.Column("feedback_json", sa.Text(), nullable=True),
        sa.Column("utc_saved_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["writing_demo_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_writing_demo_revisions_session_id",
        "writing_demo_revisions",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_writing_demo_revisions_session_id", table_name="writing_demo_revisions")
    op.drop_table("writing_demo_revisions")
    op.drop_index("ix_writing_demo_sessions_felhasznalo_nev", table_name="writing_demo_sessions")
    op.drop_table("writing_demo_sessions")
