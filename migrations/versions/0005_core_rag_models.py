"""Core immutable RAG, AgentRun, evidence, and citation models."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("active_version_id", postgresql.UUID(as_uuid=False)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("content_digest", sa.String(71), nullable=False),
        sa.Column("scope_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=False)), nullable=False),
        sa.Column("searchable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"]),
        sa.UniqueConstraint("document_id", "content_digest"),
    )
    op.create_foreign_key(
        "fk_documents_active_version",
        "knowledge_documents",
        "document_versions",
        ["active_version_id"],
        ["id"],
    )
    op.create_table(
        "retrieval_policies",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("configuration", postgresql.JSONB(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("name", "version"),
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("scope_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=False)), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("embedding", Vector()),
        sa.Column("search_vector", postgresql.TSVECTOR()),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"]),
        sa.UniqueConstraint("document_version_id", "ordinal"),
    )
    op.create_index("ix_chunks_scope_generation", "knowledge_chunks", ["generation", "active"])
    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("principal_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("query_digest", sa.String(71), nullable=False),
        sa.Column("scope_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=False)), nullable=False),
        sa.Column("authz_revision", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("answer", sa.Text()),
        sa.Column("evidence_status", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_agent_runs_owner", "agent_runs", ["principal_id", "created_at"])
    op.create_table(
        "evidence_records",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("source_version", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("scope_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=False)), nullable=False),
        sa.Column("content_digest", sa.String(71), nullable=False),
        sa.Column("validity", sa.String(30), nullable=False),
        sa.Column("authz_revision", sa.BigInteger(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
    )
    op.create_table(
        "citations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("support", sa.String(30), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_records.id"]),
    )


def downgrade() -> None:
    op.drop_table("citations")
    op.drop_table("evidence_records")
    op.drop_index("ix_agent_runs_owner", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("ix_chunks_scope_generation", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_table("retrieval_policies")
    op.drop_constraint("fk_documents_active_version", "knowledge_documents", type_="foreignkey")
    op.drop_table("document_versions")
    op.drop_table("knowledge_documents")
