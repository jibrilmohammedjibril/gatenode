"""add structured user name fields

Revision ID: 9b1c2d3e4f5a
Revises: 7c8d9e0f1a2b
Create Date: 2026-03-21 18:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9b1c2d3e4f5a"
down_revision: Union[str, None] = "7c8d9e0f1a2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _split_person_name(full_name: str | None) -> tuple[str | None, str | None, str | None]:
    parts = [part for part in (full_name or "").split() if part]
    if not parts:
        return None, None, None
    if len(parts) == 1:
        return parts[0], None, parts[0]
    if len(parts) == 2:
        return parts[0], None, parts[1]
    return parts[0], " ".join(parts[1:-1]), parts[-1]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("users")}

    if "first_name" not in columns:
        op.add_column("users", sa.Column("first_name", sa.String(), nullable=True))

    if "middle_name" not in columns:
        op.add_column("users", sa.Column("middle_name", sa.String(), nullable=True))

    if "last_name" not in columns:
        op.add_column("users", sa.Column("last_name", sa.String(), nullable=True))

    rows = bind.execute(sa.text("SELECT id, full_name, first_name, middle_name, last_name FROM users")).mappings().all()
    for row in rows:
        if row.get("first_name") or row.get("middle_name") or row.get("last_name"):
            continue
        first_name, middle_name, last_name = _split_person_name(row.get("full_name"))
        bind.execute(
            sa.text(
                """
                UPDATE users
                SET first_name = :first_name,
                    middle_name = :middle_name,
                    last_name = :last_name
                WHERE id = :user_id
                """
            ),
            {
                "user_id": row["id"],
                "first_name": first_name,
                "middle_name": middle_name,
                "last_name": last_name,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("users")}

    if "last_name" in columns:
        op.drop_column("users", "last_name")

    if "middle_name" in columns:
        op.drop_column("users", "middle_name")

    if "first_name" in columns:
        op.drop_column("users", "first_name")
