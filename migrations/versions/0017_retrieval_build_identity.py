"""Version retrieval projections and isolate reusable embeddings by model and scope."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("document_versions", sa.Column("build_profile", postgresql.JSONB()))
    op.add_column("knowledge_chunks", sa.Column("embedding_profile", sa.String(64)))
    op.add_column("knowledge_chunks", sa.Column("lexical_version", sa.String(64)))
    op.add_column("knowledge_chunks", sa.Column("section_key", sa.String(64)))
    op.create_index(
        "ix_knowledge_chunks_lexical_active",
        "knowledge_chunks",
        ["search_vector"],
        postgresql_using="gin",
        postgresql_where=sa.text("active = true"),
    )
    op.create_table(
        "knowledge_embedding_cache",
        sa.Column("profile", sa.String(64), primary_key=True),
        sa.Column("scope_key", sa.String(64), primary_key=True),
        sa.Column("content_digest", sa.String(64), primary_key=True),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_lexical_active", table_name="knowledge_chunks")
    op.drop_table("knowledge_embedding_cache")
    for column in ("section_key", "lexical_version", "embedding_profile"):
        op.drop_column("knowledge_chunks", column)
    op.drop_column("document_versions", "build_profile")
