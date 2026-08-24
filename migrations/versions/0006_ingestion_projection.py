"""Governed ingestion metadata, projections, jobs, and immutable version fields.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("source_key", sa.String(300), nullable=False, server_default="legacy"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("owner_principal_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "scope_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=False)),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_unique_constraint(
        "uq_knowledge_documents_source_key",
        "knowledge_documents",
        ["source_key"],
    )

    op.add_column(
        "document_versions",
        sa.Column("version_label", sa.String(100), nullable=False, server_default="v1"),
    )
    op.add_column(
        "document_versions", sa.Column("object_key", sa.String(1_024), nullable=True)
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "media_type",
            sa.String(200),
            nullable=False,
            server_default="application/octet-stream",
        ),
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "size_bytes",
            sa.BigInteger(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "document_versions",
        sa.Column("metadata_schema_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "document_versions",
        sa.Column("lifecycle_state", sa.String(30), nullable=False, server_default="UPLOADED"),
    )
    op.add_column(
        "document_versions",
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column("supersedes_version_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        "fk_document_versions_supersedes",
        "document_versions",
        "document_versions",
        ["supersedes_version_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_document_versions_label", "document_versions", ["document_id", "version_label"]
    )

    op.create_table(
        "document_metadata",
        sa.Column("document_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("review_status", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"]),
        sa.PrimaryKeyConstraint("document_version_id", "key"),
    )
    op.create_table(
        "knowledge_projections",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("projection_type", sa.String(20), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("adapter_version", sa.String(100), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("record_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"]),
        sa.UniqueConstraint(
            "document_version_id",
            "projection_type",
            "generation",
            name="uq_projection_generation",
        ),
    )
    op.create_index(
        "ix_projection_ready_generation",
        "knowledge_projections",
        ["projection_type", "generation", "state"],
    )
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("current_stage", sa.String(30), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("idempotency_key", sa.String(300), nullable=False),
        sa.Column("lease_owner", sa.String(200), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.Column("failure_detail_ref", sa.String(1_024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"]),
        sa.UniqueConstraint(
            "document_version_id", "idempotency_key", name="uq_ingestion_job_idempotency"
        ),
    )
    op.create_index(
        "ix_ingestion_jobs_claim",
        "ingestion_jobs",
        ["state", "lease_until", "created_at"],
    )
    op.create_table(
        "object_write_intents",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("object_key", sa.String(1_024), nullable=False),
        sa.Column("content_digest", sa.String(71), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"]),
        sa.UniqueConstraint("object_key", name="uq_object_write_intent_key"),
    )


def downgrade() -> None:
    op.drop_table("object_write_intents")
    op.drop_index("ix_ingestion_jobs_claim", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_index("ix_projection_ready_generation", table_name="knowledge_projections")
    op.drop_table("knowledge_projections")
    op.drop_table("document_metadata")
    op.drop_constraint("uq_document_versions_label", "document_versions", type_="unique")
    op.drop_constraint("fk_document_versions_supersedes", "document_versions", type_="foreignkey")
    for column in (
        "supersedes_version_id",
        "created_by",
        "lifecycle_state",
        "metadata_schema_version",
        "size_bytes",
        "media_type",
        "object_key",
        "version_label",
    ):
        op.drop_column("document_versions", column)
    op.drop_constraint("uq_knowledge_documents_source_key", "knowledge_documents", type_="unique")
    for column in (
        "updated_at",
        "created_at",
        "status",
        "scope_ids",
        "owner_principal_id",
        "source_key",
    ):
        op.drop_column("knowledge_documents", column)
