"""add sub_admin to householdrole

Revision ID: d88c07d11adf
Revises: ddbe86a0cc81
Create Date: 2026-01-31 12:05:08.712083

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd88c07d11adf'
down_revision: Union[str, None] = 'ddbe86a0cc81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'sub_admin' to the enum
    op.execute("ALTER TYPE householdrole ADD VALUE IF NOT EXISTS 'sub_admin'")

def downgrade() -> None:
    # Postgres enums are hard to downgrade (require re-creating type).
    # For now, we leave it or manual intervention.
    pass
