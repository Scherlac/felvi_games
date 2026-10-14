"""rename writing prototype tables to product-domain names

Revision ID: d8f1c7a3b640
Revises: c9d4f2a61b38
Create Date: 2026-10-14

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "d8f1c7a3b640"
down_revision: str | None = "c9d4f2a61b38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.rename_table("writing_demo_sessions", "writing_practice_sessions")
    op.rename_table("writing_demo_revisions", "writing_draft_revisions")
    op.rename_table("writing_demo_messages", "writing_tutor_messages")

    op.drop_index(
        "ix_writing_demo_sessions_felhasznalo_nev",
        table_name="writing_practice_sessions",
    )
    op.create_index(
        "ix_writing_practice_sessions_felhasznalo_nev",
        "writing_practice_sessions",
        ["felhasznalo_nev"],
        unique=False,
    )
    op.drop_index("ix_writing_demo_revisions_session_id", table_name="writing_draft_revisions")
    op.create_index(
        "ix_writing_draft_revisions_session_id",
        "writing_draft_revisions",
        ["session_id"],
        unique=False,
    )
    op.drop_index("ix_writing_demo_messages_session_id", table_name="writing_tutor_messages")
    op.create_index(
        "ix_writing_tutor_messages_session_id",
        "writing_tutor_messages",
        ["session_id"],
        unique=False,
    )
    op.add_column(
        "writing_practice_sessions",
        sa.Column(
            "task_metadata_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.execute(
        "UPDATE writing_practice_sessions "
        "SET task_metadata_json = "
        "'{\"source_kind\":\"legacy_practice\",\"title\":\"Earlier writing session\"}'"
    )


def downgrade() -> None:
    op.drop_column("writing_practice_sessions", "task_metadata_json")
    op.drop_index("ix_writing_tutor_messages_session_id", table_name="writing_tutor_messages")
    op.drop_index("ix_writing_draft_revisions_session_id", table_name="writing_draft_revisions")
    op.drop_index(
        "ix_writing_practice_sessions_felhasznalo_nev",
        table_name="writing_practice_sessions",
    )

    op.rename_table("writing_tutor_messages", "writing_demo_messages")
    op.rename_table("writing_draft_revisions", "writing_demo_revisions")
    op.rename_table("writing_practice_sessions", "writing_demo_sessions")

    op.create_index(
        "ix_writing_demo_sessions_felhasznalo_nev",
        "writing_demo_sessions",
        ["felhasznalo_nev"],
        unique=False,
    )
    op.create_index(
        "ix_writing_demo_revisions_session_id",
        "writing_demo_revisions",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_writing_demo_messages_session_id",
        "writing_demo_messages",
        ["session_id"],
        unique=False,
    )
