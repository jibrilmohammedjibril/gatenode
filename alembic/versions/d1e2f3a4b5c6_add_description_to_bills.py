"""add description to bills

Revision ID: d1e2f3a4b5c6
Revises: c6f4b2780e21
Create Date: 2026-05-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c6f4b2780e21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("bills", "description")
