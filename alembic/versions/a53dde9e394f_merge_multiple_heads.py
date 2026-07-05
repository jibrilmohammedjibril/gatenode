"""Merge multiple heads

Revision ID: a53dde9e394f
Revises: 68152d5f4ea8, 9b7d7e254aaf
Create Date: 2026-01-14 23:43:57.390481

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a53dde9e394f'
down_revision: Union[str, None] = ('68152d5f4ea8', '9b7d7e254aaf')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
