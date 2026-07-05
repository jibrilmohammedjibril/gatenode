"""add_checkin_checkout_timestamps

Revision ID: 8ddd0d97c373
Revises: c4c66f8f6758
Create Date: 2026-02-17 15:29:28.850347

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8ddd0d97c373'
down_revision: Union[str, None] = 'c4c66f8f6758'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('visitor_invites', sa.Column('checked_in_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('visitor_invites', sa.Column('checked_out_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('visitor_invites', 'checked_out_at')
    op.drop_column('visitor_invites', 'checked_in_at')
