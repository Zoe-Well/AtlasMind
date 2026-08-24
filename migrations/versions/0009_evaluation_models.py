"""Versioned evaluation datasets, results, and operational access grants.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_datasets",
        sa.Column("id", sa.String(200), nullable=False),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("split", sa.String(30), nullable=False),
        sa.Column("knowledge_snapshot_digest", sa.String(71), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.PrimaryKeyConstraint("id", "version"),
    )
    op.create_table(
        "evaluation_cases",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("dataset_id", sa.String(200), nullable=False),
        sa.Column("dataset_version", sa.String(100), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("question_ref", sa.Text(), nullable=False),
        sa.Column(
            "allowed_scope_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=False)),
            nullable=False,
        ),
        sa.Column("expected_evidence", postgresql.JSONB(), nullable=False),
        sa.Column("forbidden_evidence", postgresql.JSONB(), nullable=False),
        sa.Column("answer_points", postgresql.JSONB(), nullable=False),
        sa.Column("expected_behavior", sa.String(30), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id", "dataset_version"],
            ["evaluation_datasets.id", "evaluation_datasets.version"],
        ),
        sa.UniqueConstraint(
            "dataset_id",
            "dataset_version",
            "ordinal",
            name="uq_evaluation_case_ordinal",
        ),
    )
    op.create_table(
        "evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("dataset_id", sa.String(200), nullable=False),
        sa.Column("dataset_version", sa.String(100), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("manifest_digest", sa.String(71)),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("report_ref", sa.Text()),
        sa.ForeignKeyConstraint(
            ["dataset_id", "dataset_version"],
            ["evaluation_datasets.id", "evaluation_datasets.version"],
        ),
    )
    op.create_index(
        "ix_evaluation_runs_requester",
        "evaluation_runs",
        ["requested_by", "created_at"],
    )
    op.create_table(
        "evaluation_results",
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("safety_failures", postgresql.ARRAY(sa.String(100)), nullable=False),
        sa.Column("failure_sample_ref", sa.Text()),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["evaluation_runs.id"]),
        sa.ForeignKeyConstraint(["case_id"], ["evaluation_cases.id"]),
        sa.PrimaryKeyConstraint("evaluation_run_id", "case_id"),
    )
    op.create_table(
        "operational_record_access_grants",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("principal_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "principal_id",
            "resource_type",
            "resource_id",
            "action",
            name="uq_operational_record_grant",
        ),
    )


def downgrade() -> None:
    op.drop_table("operational_record_access_grants")
    op.drop_table("evaluation_results")
    op.drop_index("ix_evaluation_runs_requester", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_table("evaluation_cases")
    op.drop_table("evaluation_datasets")
