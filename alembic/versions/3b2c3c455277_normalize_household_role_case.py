"""normalize_household_role_case

Revision ID: 3b2c3c455277
Revises: d88c07d11adf
Create Date: 2026-01-31 13:39:10.345615

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b2c3c455277'
down_revision: Union[str, None] = 'd88c07d11adf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add lowercase values to the Enum type
    # Postgres requires committing new Enum values before using them.
    # We use autocommit_block() to ensure they are available for the UPDATE.
    with op.get_context().autocommit_block():
        roles = ['admin', 'spouse', 'child', 'parent', 'relative', 'staff', 'other']
        for r in roles:
            op.execute(f"ALTER TYPE householdrole ADD VALUE IF NOT EXISTS '{r}'")
    
    # 2. Update existing data to lowercase
    # Cast to text, lowercase it, cast back to enum
    op.execute("UPDATE user_units SET role = lower(role::text)::householdrole")

def downgrade() -> None:
    # Cannot easily remove enum values. 
    # Logic could be to update back to Upper? But we want strict lowercase now.
    pass
