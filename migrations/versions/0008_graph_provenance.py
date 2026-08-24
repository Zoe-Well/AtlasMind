"""Canonical graph entities, source mentions, relations, and evidence.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "graph_entities",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("merged_into_id", postgresql.UUID(as_uuid=False)),
        sa.ForeignKeyConstraint(["merged_into_id"], ["graph_entities.id"]),
        sa.UniqueConstraint("canonical_name", "entity_type", name="uq_graph_entity_name_type"),
    )
    op.create_table(
        "entity_mentions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("surface", sa.Text(), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("scope_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=False)), nullable=False),
        sa.Column("extraction_version", sa.String(100), nullable=False),
        sa.Column("review_status", sa.String(20), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["graph_entities.id"]),
        sa.ForeignKeyConstraint(["chunk_id"], ["knowledge_chunks.id"]),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"]),
    )
    op.create_table(
        "graph_relations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("source_entity_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("relation_type", sa.String(100), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("extraction_version", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(["source_entity_id"], ["graph_entities.id"]),
        sa.ForeignKeyConstraint(["target_entity_id"], ["graph_entities.id"]),
        sa.UniqueConstraint(
            "source_entity_id",
            "target_entity_id",
            "relation_type",
            "extraction_version",
            name="uq_graph_relation_version",
        ),
    )
    op.create_table(
        "relation_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("relation_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("scope_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=False)), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["relation_id"], ["graph_relations.id"]),
        sa.ForeignKeyConstraint(["chunk_id"], ["knowledge_chunks.id"]),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"]),
        sa.UniqueConstraint("relation_id", "chunk_id", name="uq_relation_chunk_evidence"),
    )
    op.create_index(
        "ix_relation_evidence_version_generation",
        "relation_evidence",
        ["document_version_id", "generation"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_relation_evidence_version_generation",
        table_name="relation_evidence",
    )
    op.drop_table("relation_evidence")
    op.drop_table("graph_relations")
    op.drop_table("entity_mentions")
    op.drop_table("graph_entities")
