"""add incidents table

Revision ID: c9f1d2e3a4b5
Revises: add_gender_guests_recurring, 65bc43debfc4, role_and_wallet_v1
Create Date: 2026-05-17 21:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c9f1d2e3a4b5"
down_revision = ("add_gender_guests_recurring", "65bc43debfc4", "role_and_wallet_v1")
branch_labels = None
depends_on = None


incident_category_enum = sa.Enum("security", name="incident_category")
incident_priority_enum = sa.Enum("low", "medium", "high", name="incident_priority")
incident_status_enum = sa.Enum("pending", "investigating", "resolved", "closed", name="incident_status")


def upgrade() -> None:
    bind = op.get_bind()
    incident_category_enum.create(bind, checkfirst=True)
    incident_priority_enum.create(bind, checkfirst=True)
    incident_status_enum.create(bind, checkfirst=True)

    op.execute("CREATE SEQUENCE IF NOT EXISTS incident_ticket_number_seq START 1")

    op.create_table(
        "incidents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("ticket_number", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", incident_category_enum, nullable=False),
        sa.Column("priority", incident_priority_enum, nullable=False),
        sa.Column("status", incident_status_enum, nullable=False),
        sa.Column("attachments", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("unit_id", sa.String(), nullable=True),
        sa.Column("estate_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["estate_id"], ["estates.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_incidents_ticket_number"), "incidents", ["ticket_number"], unique=True)
    op.create_index(op.f("ix_incidents_estate_id"), "incidents", ["estate_id"], unique=False)
    op.create_index(op.f("ix_incidents_user_id"), "incidents", ["user_id"], unique=False)
    op.create_index(op.f("ix_incidents_created_at"), "incidents", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_incidents_created_at"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_user_id"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_estate_id"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_ticket_number"), table_name="incidents")
    op.drop_table("incidents")
    op.execute("DROP SEQUENCE IF EXISTS incident_ticket_number_seq")

    bind = op.get_bind()
    incident_status_enum.drop(bind, checkfirst=True)
    incident_priority_enum.drop(bind, checkfirst=True)
    incident_category_enum.drop(bind, checkfirst=True)
