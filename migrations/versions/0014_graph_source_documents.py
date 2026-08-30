"""Direct source-document provenance for graph observations.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in ("entity_mentions", "relation_evidence"):
        op.add_column(
            table_name,
            sa.Column("source_document_id", postgresql.UUID(as_uuid=False), nullable=True),
        )
        op.execute(
            f"""
            UPDATE {table_name} provenance
               SET source_document_id = version.document_id
              FROM document_versions version
             WHERE version.id = provenance.document_version_id
            """
        )
        op.alter_column(table_name, "source_document_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table_name}_source_document",
            table_name,
            "knowledge_documents",
            ["source_document_id"],
            ["id"],
        )
        op.create_index(
            f"ix_{table_name}_source_document",
            table_name,
            ["source_document_id"],
        )


def downgrade() -> None:
    for table_name in ("relation_evidence", "entity_mentions"):
        op.drop_index(f"ix_{table_name}_source_document", table_name=table_name)
        op.drop_constraint(
            f"fk_{table_name}_source_document",
            table_name,
            type_="foreignkey",
        )
        op.drop_column(table_name, "source_document_id")
