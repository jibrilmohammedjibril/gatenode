"""merge_divergent_heads

Revision ID: 62f6cdd80589
Revises: 31cc599f8d38, ba15e0908bf9
Create Date: 2025-12-25 20:03:08.415498

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '62f6cdd80589'
down_revision: Union[str, None] = ('31cc599f8d38', 'ba15e0908bf9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
