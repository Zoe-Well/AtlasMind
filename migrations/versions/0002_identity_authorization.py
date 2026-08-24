"""Create identity, role, scope, and grant tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "principals",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("authz_revision", sa.BigInteger(), nullable=False, server_default="1"),
        sa.UniqueConstraint("issuer", "subject", name="uq_principal_issuer_subject"),
    )
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("code", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "knowledge_scopes",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("code", sa.String(200), nullable=False, unique=True),
        sa.Column("classification", sa.String(50), nullable=False),
        sa.Column("policy_revision", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "role_assignments",
        sa.Column(
            "principal_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("principals.id"),
            primary_key=True,
        ),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("roles.id"),
            primary_key=True,
        ),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "scope_grants",
        sa.Column("subject_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("subject_type", sa.String(20), nullable=False),
        sa.Column(
            "scope_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("knowledge_scopes.id"),
            nullable=False,
        ),
        sa.Column("actions", postgresql.ARRAY(sa.String(100)), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("subject_id", "subject_type", "scope_id"),
    )


def downgrade() -> None:
    op.drop_table("scope_grants")
    op.drop_table("role_assignments")
    op.drop_table("knowledge_scopes")
    op.drop_table("roles")
    op.drop_table("principals")
