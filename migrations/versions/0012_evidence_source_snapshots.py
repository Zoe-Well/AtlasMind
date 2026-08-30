"""Persist generic citation source snapshots for Agent capabilities.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evidence_records", sa.Column("source_title", sa.Text()))
    op.add_column("evidence_records", sa.Column("source_excerpt", sa.Text()))
    op.add_column(
        "evidence_records",
        sa.Column(
            "source_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute(
        """
        UPDATE evidence_records evidence
        SET source_title = document.title,
            source_excerpt = LEFT(chunk.content, 500),
            source_metadata = jsonb_build_object(
                'canonicalId', evidence.source_id::text,
                'version', evidence.source_version::text
            )
        FROM knowledge_chunks chunk
        JOIN document_versions version ON version.id = chunk.document_version_id
        JOIN knowledge_documents document ON document.id = version.document_id
        WHERE evidence.source_type = 'DOCUMENT'
          AND evidence.source_id = chunk.id
          AND evidence.source_version = version.id
        """
    )


def downgrade() -> None:
    op.drop_column("evidence_records", "source_metadata")
    op.drop_column("evidence_records", "source_excerpt")
    op.drop_column("evidence_records", "source_title")
