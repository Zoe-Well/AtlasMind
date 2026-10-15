"""Persist conversation membership and user messages alongside run results."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("principal_id", postgresql.UUID(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("id", "principal_id", name="uq_conversation_owner"),
    )
    op.create_index(
        "ix_conversations_owner_updated", "conversations", ["principal_id", "updated_at", "id"]
    )
    op.add_column("agent_runs", sa.Column("conversation_id", postgresql.UUID()))
    op.add_column("agent_runs", sa.Column("turn_index", sa.Integer()))
    op.add_column("agent_runs", sa.Column("query_text", sa.Text()))
    op.create_foreign_key(
        "fk_run_conversation_owner",
        "agent_runs",
        "conversations",
        ["conversation_id", "principal_id"],
        ["id", "principal_id"],
    )
    op.create_unique_constraint(
        "uq_conversation_turn", "agent_runs", ["conversation_id", "turn_index"]
    )
    op.create_check_constraint(
        "ck_conversation_turn",
        "agent_runs",
        "conversation_id IS NULL OR (turn_index IS NOT NULL AND turn_index > 0)",
    )
    # Old records have no recoverable original question or reliable conversation grouping.
    # Preserve each as one distinct turn, with query_text NULL (never fabricate a question).
    op.execute("""
        INSERT INTO conversations (id, principal_id, title, created_at, updated_at)
        SELECT id, principal_id, '历史问答 · 原问题未保存', created_at,
               COALESCE(finished_at, created_at)
        FROM agent_runs
    """)
    op.execute("UPDATE agent_runs SET conversation_id = id, turn_index = 1")


def downgrade() -> None:
    op.drop_constraint("ck_conversation_turn", "agent_runs", type_="check")
    op.drop_constraint("uq_conversation_turn", "agent_runs", type_="unique")
    op.drop_constraint("fk_run_conversation_owner", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "query_text")
    op.drop_column("agent_runs", "turn_index")
    op.drop_column("agent_runs", "conversation_id")
    op.drop_table("conversations")
