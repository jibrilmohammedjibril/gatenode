"""Add user import jobs and unit address metadata

Revision ID: b7e1c0a9d4f2
Revises: a4f9c2b7d1e3
Create Date: 2026-03-28 21:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b7e1c0a9d4f2"
down_revision: Union[str, None] = "a4f9c2b7d1e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


userimportjobstatus = sa.Enum(
    "PENDING",
    "PROCESSING",
    "COMPLETED",
    "COMPLETED_WITH_ERRORS",
    "FAILED",
    name="userimportjobstatus",
)

userimportjobstatus_column = postgresql.ENUM(
    "PENDING",
    "PROCESSING",
    "COMPLETED",
    "COMPLETED_WITH_ERRORS",
    "FAILED",
    name="userimportjobstatus",
    create_type=False,
)


def upgrade() -> None:
    op.add_column("units", sa.Column("address_metadata", sa.JSON(), nullable=True))

    userimportjobstatus.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "user_import_jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("estate_id", sa.String(), nullable=False),
        sa.Column("created_by_user_id", sa.String(), nullable=False),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("status", userimportjobstatus_column, nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("processed_rows", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("source_rows", sa.JSON(), nullable=False),
        sa.Column("results_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["estate_id"], ["estates.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_import_jobs_created_by_user_id"), "user_import_jobs", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_user_import_jobs_estate_id"), "user_import_jobs", ["estate_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_import_jobs_estate_id"), table_name="user_import_jobs")
    op.drop_index(op.f("ix_user_import_jobs_created_by_user_id"), table_name="user_import_jobs")
    op.drop_table("user_import_jobs")
    userimportjobstatus.drop(op.get_bind(), checkfirst=True)

    op.drop_column("units", "address_metadata")
