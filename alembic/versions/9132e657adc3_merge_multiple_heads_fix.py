"""merge_multiple_heads_fix

Revision ID: 9132e657adc3
Revises: add_gender_guests_recurring, e67f4cb7f908
Create Date: 2026-02-18 16:55:33.425082

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9132e657adc3'
down_revision: Union[str, None] = ('add_gender_guests_recurring', 'e67f4cb7f908')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
