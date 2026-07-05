"""add_checked_in_by_to_visitor_invites

Revision ID: e67f4cb7f908
Revises: 8ddd0d97c373
Create Date: 2026-02-17 15:47:21.869172

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e67f4cb7f908'
down_revision: Union[str, None] = '8ddd0d97c373'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('visitor_invites', sa.Column('checked_in_by', sa.String(), sa.ForeignKey('users.id'), nullable=True))


def downgrade() -> None:
    op.drop_column('visitor_invites', 'checked_in_by')
