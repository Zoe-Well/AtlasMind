"""Allow immutable objects to be referenced by multiple document versions.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_object_write_intent_key", "object_write_intents", type_="unique")
    op.create_index(
        "ix_object_write_intents_object_key",
        "object_write_intents",
        ["object_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_object_write_intents_object_key", table_name="object_write_intents")
    op.create_unique_constraint(
        "uq_object_write_intent_key", "object_write_intents", ["object_key"]
    )
