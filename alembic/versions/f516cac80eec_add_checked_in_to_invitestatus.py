"""Add CHECKED_IN to InviteStatus

Revision ID: f516cac80eec
Revises: 3b2c3c455277
Create Date: 2026-02-05 14:32:32.629403

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f516cac80eec'
down_revision: Union[str, None] = '3b2c3c455277'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use autocommit block because ALTER TYPE ... ADD VALUE cannot run inside a transaction
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE invitestatus ADD VALUE IF NOT EXISTS 'checked_in'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from ENUM types easily.
    pass
