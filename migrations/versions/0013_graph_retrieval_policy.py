"""High-quality auxiliary graph policy, resolution, and provenance state.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.add_column("graph_entities", sa.Column("normalized_name", sa.Text(), nullable=True))
    op.add_column("graph_entities", sa.Column("embedding", Vector(), nullable=True))
    op.add_column(
        "graph_entities",
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.add_column(
        "graph_entities",
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.execute(
        """
        UPDATE graph_entities
           SET normalized_name = regexp_replace(lower(canonical_name), '[^a-z0-9一-龥]+', '', 'g')
        """
    )
    op.alter_column("graph_entities", "normalized_name", nullable=False)
    op.create_unique_constraint(
        "uq_graph_entity_normalized_type",
        "graph_entities",
        ["normalized_name", "entity_type"],
    )
    op.create_index(
        "ix_graph_entity_normalized_trgm",
        "graph_entities",
        ["normalized_name"],
        postgresql_using="gin",
        postgresql_ops={"normalized_name": "gin_trgm_ops"},
    )

    op.add_column(
        "entity_mentions",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "entity_mentions",
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "entity_mentions",
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_entity_mentions_active_version",
        "entity_mentions",
        ["document_version_id", "active"],
    )

    op.add_column(
        "relation_evidence",
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
    )
    op.add_column(
        "relation_evidence",
        sa.Column("extraction_version", sa.String(100), nullable=False, server_default="legacy"),
    )
    op.add_column(
        "relation_evidence",
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "relation_evidence",
        sa.Column("decision", sa.String(20), nullable=False, server_default="CANDIDATE"),
    )
    op.add_column(
        "relation_evidence",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "relation_evidence",
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.add_column(
        "relation_evidence", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_relation_evidence_retrieval",
        "relation_evidence",
        ["active", "decision", "document_version_id"],
    )

    op.drop_constraint("uq_graph_relation_version", "graph_relations", type_="unique")
    op.create_unique_constraint(
        "uq_graph_relation_identity",
        "graph_relations",
        ["source_entity_id", "target_entity_id", "relation_type"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_graph_relation_identity", "graph_relations", type_="unique")
    op.create_unique_constraint(
        "uq_graph_relation_version",
        "graph_relations",
        ["source_entity_id", "target_entity_id", "relation_type", "extraction_version"],
    )
    op.drop_index("ix_relation_evidence_retrieval", table_name="relation_evidence")
    for column in (
        "retired_at",
        "created_at",
        "active",
        "decision",
        "policy_version",
        "extraction_version",
        "confidence",
    ):
        op.drop_column("relation_evidence", column)
    op.drop_index("ix_entity_mentions_active_version", table_name="entity_mentions")
    for column in ("created_at", "policy_version", "active"):
        op.drop_column("entity_mentions", column)
    op.drop_index("ix_graph_entity_normalized_trgm", table_name="graph_entities")
    op.drop_constraint("uq_graph_entity_normalized_type", "graph_entities", type_="unique")
    for column in ("updated_at", "created_at", "embedding", "normalized_name"):
        op.drop_column("graph_entities", column)
