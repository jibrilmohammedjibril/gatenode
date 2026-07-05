"""normalize email columns

Revision ID: 6f0e2f8a6c41
Revises: 849266eb7f47, d1e2f3a4b5c6, d3099dcdd346
Create Date: 2026-05-19 10:15:00.000000

"""
from collections import defaultdict
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6f0e2f8a6c41"
down_revision: Union[str, tuple[str, ...], None] = (
    "849266eb7f47",
    "d1e2f3a4b5c6",
    "d3099dcdd346",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalized_email(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip().lower()
    return normalized or None


def _find_case_collisions(rows: Sequence[dict[str, str]]) -> dict[str, list[tuple[str, str]]]:
    collisions: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for row in rows:
        normalized = _normalized_email(row["email"])
        if not normalized:
            continue
        collisions[normalized].append((str(row["id"]), row["email"]))

    return {
        normalized: values
        for normalized, values in collisions.items()
        if len(values) > 1
    }


def _raise_on_case_collisions(table_name: str, collisions: dict[str, list[tuple[str, str]]]) -> None:
    if not collisions:
        return

    lines = []
    for normalized, values in sorted(collisions.items()):
        rendered_rows = ", ".join(f"{row_id}:{email}" for row_id, email in values)
        lines.append(f"{normalized} -> {rendered_rows}")

    raise RuntimeError(
        f"Cannot normalize {table_name} emails because multiple rows collapse to the same lowercase value: "
        + "; ".join(lines)
    )


def upgrade() -> None:
    connection = op.get_bind()

    user_rows = connection.execute(
        sa.text("SELECT id, email FROM users WHERE email IS NOT NULL")
    ).mappings().all()
    _raise_on_case_collisions("users", _find_case_collisions(user_rows))

    two_factor_rows = connection.execute(
        sa.text("SELECT id, email FROM two_factor_auth WHERE email IS NOT NULL")
    ).mappings().all()
    _raise_on_case_collisions("two_factor_auth", _find_case_collisions(two_factor_rows))

    connection.execute(
        sa.text(
            """
            UPDATE users
            SET email = lower(trim(email))
            WHERE email IS NOT NULL AND email <> lower(trim(email))
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE otp_codes
            SET email = lower(trim(email))
            WHERE email IS NOT NULL AND email <> lower(trim(email))
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE two_factor_auth
            SET email = lower(trim(email))
            WHERE email IS NOT NULL AND email <> lower(trim(email))
            """
        )
    )


def downgrade() -> None:
    pass
