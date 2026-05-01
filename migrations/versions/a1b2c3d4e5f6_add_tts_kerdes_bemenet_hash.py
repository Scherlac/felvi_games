"""add_tts_kerdes_bemenet_hash

Revision ID: a1b2c3d4e5f6
Revises: c491db828a78
Create Date: 2026-05-01 00:00:00.000000

Adds a short SHA256 hash column to feladatok that records which raw TTS input
was used to generate the cached audio.  tts_kerdes_szoveg stores the
LLM-processed spoken text; this column stores a hash of the raw markdown so
we can detect when the input has changed (stale detection).
"""
from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = ('c491db828a78', 'aacfdfc25f9b')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('feladatok', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tts_kerdes_bemenet_hash', sa.String(length=16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('feladatok', schema=None) as batch_op:
        batch_op.drop_column('tts_kerdes_bemenet_hash')
