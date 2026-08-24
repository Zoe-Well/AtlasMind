"""Controlled Agent steps, capability registry, tool invocations, and approvals.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("task_type", sa.String(30), nullable=False, server_default="SIMPLE"),
    )
    op.add_column(
        "agent_runs",
        sa.Column("budgets", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "agent_runs",
        sa.Column("usage", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column("agent_runs", sa.Column("degradation_reason", sa.String(100)))

    op.create_table(
        "capability_definitions",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("input_schema", postgresql.JSONB(), nullable=False),
        sa.Column("output_schema", postgresql.JSONB(), nullable=False),
        sa.Column("required_actions", postgresql.ARRAY(sa.String(100)), nullable=False),
        sa.Column("supported_scope_types", postgresql.ARRAY(sa.String(100)), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("side_effect", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("idempotency_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("timeout_ms", sa.Integer(), nullable=False),
        sa.Column("max_result_bytes", sa.BigInteger(), nullable=False),
        sa.Column("max_items", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.PrimaryKeyConstraint("name", "version"),
    )
    op.create_table(
        "run_steps",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("capability_name", sa.String(200)),
        sa.Column("capability_version", sa.String(100)),
        sa.Column("input_digest", sa.String(71)),
        sa.Column("result_ref", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_run_step_ordinal"),
    )
    op.create_table(
        "tool_invocations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("run_step_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("capability_name", sa.String(200), nullable=False),
        sa.Column("capability_version", sa.String(100), nullable=False),
        sa.Column("principal_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("authz_revision", sa.BigInteger(), nullable=False),
        sa.Column("normalized_input_digest", sa.String(71), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("approval_request_id", postgresql.UUID(as_uuid=False)),
        sa.Column("result_ref", sa.Text()),
        sa.Column("error_code", sa.String(100)),
        sa.Column("idempotency_key", sa.String(200)),
        sa.ForeignKeyConstraint(["run_step_id"], ["run_steps.id"]),
        sa.UniqueConstraint(
            "capability_name",
            "idempotency_key",
            name="uq_tool_side_effect_idempotency",
        ),
    )
    op.create_table(
        "approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("invocation_id", postgresql.UUID(as_uuid=False), nullable=False, unique=True),
        sa.Column("principal_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("capability_name", sa.String(200), nullable=False),
        sa.Column("capability_version", sa.String(100), nullable=False),
        sa.Column("target_resource", sa.Text(), nullable=False),
        sa.Column("input_digest", sa.String(71), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("nonce_hash", sa.String(71), nullable=False, unique=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=False)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["invocation_id"], ["tool_invocations.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
    )
    op.create_foreign_key(
        "fk_tool_invocation_approval",
        "tool_invocations",
        "approval_requests",
        ["approval_request_id"],
        ["id"],
    )
    op.create_index(
        "ix_approval_pending_expiry",
        "approval_requests",
        ["state", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_approval_pending_expiry", table_name="approval_requests")
    op.drop_constraint(
        "fk_tool_invocation_approval",
        "tool_invocations",
        type_="foreignkey",
    )
    op.drop_table("approval_requests")
    op.drop_table("tool_invocations")
    op.drop_table("run_steps")
    op.drop_table("capability_definitions")
    op.drop_column("agent_runs", "degradation_reason")
    op.drop_column("agent_runs", "usage")
    op.drop_column("agent_runs", "budgets")
    op.drop_column("agent_runs", "task_type")
