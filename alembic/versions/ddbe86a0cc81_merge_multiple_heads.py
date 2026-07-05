"""merge_multiple_heads

Revision ID: ddbe86a0cc81
Revises: 3dcac92aac39, f08be057730e, role_and_wallet_v1
Create Date: 2026-01-30 22:51:51.581224

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ddbe86a0cc81'
down_revision: Union[str, None] = ('3dcac92aac39', 'f08be057730e', 'role_and_wallet_v1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
