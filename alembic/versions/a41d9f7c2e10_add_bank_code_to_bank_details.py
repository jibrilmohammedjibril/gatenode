"""add bank code to bank details

Revision ID: a41d9f7c2e10
Revises: f9a4c2d7b6e1
Create Date: 2026-04-10 10:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a41d9f7c2e10"
down_revision: Union[str, None] = "f9a4c2d7b6e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bank_details", sa.Column("bank_code", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("bank_details", "bank_code")
