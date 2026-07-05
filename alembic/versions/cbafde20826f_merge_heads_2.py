"""Merge heads 2

Revision ID: cbafde20826f
Revises: a53dde9e394f
Create Date: 2026-01-14 23:45:03.253345

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cbafde20826f'
down_revision: Union[str, None] = 'a53dde9e394f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
