"""Append-only audit events and integrity-chain indexes."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("event_type", sa.String(200), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_principal_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("previous_hash", sa.String(71), nullable=False),
        sa.Column("event_hash", sa.String(71), nullable=False, unique=True),
        sa.Column("classification", sa.String(30), nullable=False),
    )
    op.create_index(
        "ix_audit_actor_time",
        "audit_events",
        ["actor_principal_id", "occurred_at"],
    )
    op.create_index(
        "ix_audit_resource_time",
        "audit_events",
        ["resource_type", "resource_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_resource_time", table_name="audit_events")
    op.drop_index("ix_audit_actor_time", table_name="audit_events")
    op.drop_table("audit_events")
