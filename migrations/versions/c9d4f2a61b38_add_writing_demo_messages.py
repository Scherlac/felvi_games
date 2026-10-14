"""add persisted tutor chat messages to writing demo sessions

Revision ID: c9d4f2a61b38
Revises: b8c1df7a2e10
Create Date: 2026-10-13

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d4f2a61b38"
down_revision: str | None = "b8c1df7a2e10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "writing_demo_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("utc_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["writing_demo_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_writing_demo_messages_session_id",
        "writing_demo_messages",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_writing_demo_messages_session_id", table_name="writing_demo_messages")
    op.drop_table("writing_demo_messages")
