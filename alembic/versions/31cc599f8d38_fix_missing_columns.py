"""Fix missing columns

Revision ID: 31cc599f8d38
Revises: f2df0776510e
Create Date: 2025-12-25 20:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '31cc599f8d38'
down_revision: Union[str, None] = 'f2df0776510e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Users Table Columns
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS deletion_requested_at TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS settings_location_enabled BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS settings_push_enabled BOOLEAN DEFAULT TRUE")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS bvn_verified BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS kyc_level INTEGER DEFAULT 1")
    
    # Units Table Columns
    op.execute("ALTER TABLE units ADD COLUMN IF NOT EXISTS rent_amount INTEGER")
    op.execute("ALTER TABLE units ADD COLUMN IF NOT EXISTS next_rent_due TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE units ADD COLUMN IF NOT EXISTS virtual_account_bank VARCHAR")
    op.execute("ALTER TABLE units ADD COLUMN IF NOT EXISTS virtual_account_number VARCHAR")
    op.execute("ALTER TABLE units ADD COLUMN IF NOT EXISTS virtual_account_name VARCHAR")
    op.execute("ALTER TABLE units ADD COLUMN IF NOT EXISTS app_fee_pending INTEGER DEFAULT 1800000") # 18k in kobo is 1,800,000 ?? User said 18,000 naira. 
    # Wait, earlier summary said "1,800,000 kobo (18,000 naira)".
    # Let's verify data type. Integer is correct.

def downgrade() -> None:
    # We generally don't delete data in fix scripts to avoid accidental data loss.
    # But strictly speaking downgrade should remove them.
    op.drop_column('users', 'deletion_requested_at')
    op.drop_column('users', 'settings_location_enabled')
    op.drop_column('users', 'settings_push_enabled')
    op.drop_column('users', 'bvn_verified')
    op.drop_column('users', 'kyc_level')
    op.drop_column('units', 'rent_amount')
    op.drop_column('units', 'next_rent_due')
    op.drop_column('units', 'virtual_account_bank')
    op.drop_column('units', 'virtual_account_number')
    op.drop_column('units', 'virtual_account_name')
    op.drop_column('units', 'app_fee_pending')
