"""Persist OpenTelemetry trace identity on AgentRun records.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("trace_id", sa.String(32), nullable=True))
    op.create_index("ix_agent_runs_trace", "agent_runs", ["trace_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_runs_trace", table_name="agent_runs")
    op.drop_column("agent_runs", "trace_id")
