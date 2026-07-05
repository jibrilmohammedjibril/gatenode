"""Enable_RLS_Complaints

Revision ID: 65bc43debfc4
Revises: d3099dcdd346
Create Date: 2025-12-14 15:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '65bc43debfc4'
down_revision = 'd3099dcdd346'
branch_labels = None
depends_on = None


def upgrade():
    # Enable RLS on complaints table
    op.execute("ALTER TABLE complaints ENABLE ROW LEVEL SECURITY")
    
    # Create Policy
    # USING clause checks existing rows
    # WITH CHECK clause checks new rows (INSERT/UPDATE) - default is same as USING if not specified? 
    # Actually, default for WITH CHECK is USING expression.
    op.execute("""
        CREATE POLICY isolate_complaints ON complaints
        USING (estate_id = current_setting('app.current_estate_id', true)::VARCHAR)
    """)
    # Note: 'true' in current_setting explains "missing_ok". If missing, returns NULL?
    # If missing, we want it to return NULL so comparison fails (safe default).
    # Postgres current_setting(name, missing_ok)


def downgrade():
    op.execute("DROP POLICY isolate_complaints ON complaints")
    op.execute("ALTER TABLE complaints DISABLE ROW LEVEL SECURITY")
