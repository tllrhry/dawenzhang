"""Add national economy catalog versions and retrieval chunks."""

from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa

from app.core.config import get_settings


revision: str = "0002_national_economy_catalog"
down_revision: Union[str, Sequence[str], None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    settings = get_settings()
    op.create_table(
        "national_economy_catalog_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_hash",
            "embedding_model",
            "embedding_dimension",
            name="uq_national_economy_catalog_version_identity",
        ),
    )
    op.create_table(
        "national_economy_industry_chunks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("catalog_version_id", sa.BigInteger(), nullable=False),
        sa.Column("industry_code", sa.String(length=4), nullable=False),
        sa.Column("industry_name", sa.String(length=255), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("chunk_type", sa.String(length=32), nullable=False),
        sa.Column("embedding", Vector(settings.embedding_dimension), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["catalog_version_id"],
            ["national_economy_catalog_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "catalog_version_id",
            "industry_code",
            "source_row",
            "chunk_type",
            "text",
            name="uq_national_economy_industry_chunk_source",
        ),
    )
    op.create_index(
        op.f("ix_national_economy_industry_chunks_catalog_version_id"),
        "national_economy_industry_chunks",
        ["catalog_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_national_economy_industry_chunks_industry_code"),
        "national_economy_industry_chunks",
        ["industry_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_national_economy_industry_chunks_industry_code"),
        table_name="national_economy_industry_chunks",
    )
    op.drop_index(
        op.f("ix_national_economy_industry_chunks_catalog_version_id"),
        table_name="national_economy_industry_chunks",
    )
    op.drop_table("national_economy_industry_chunks")
    op.drop_table("national_economy_catalog_versions")
