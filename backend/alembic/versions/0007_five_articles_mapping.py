"""Add versioned five-articles mapping catalog tables."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0007_five_articles_mapping"
down_revision: Union[str, Sequence[str], None] = "0006_result_major_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "five_articles_mapping_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("scenario_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "validation_report",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'invalid')",
            name="ck_five_articles_mapping_versions_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scenario_id",
            "source_hash",
            name="uq_five_articles_mapping_versions_scenario_source_hash",
        ),
    )
    op.create_index(
        "ix_five_articles_mapping_versions_scenario_status",
        "five_articles_mapping_versions",
        ["scenario_id", "status"],
        unique=False,
    )

    op.create_table(
        "five_articles_mapping_rows",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("mapping_version_id", sa.BigInteger(), nullable=False),
        sa.Column("scenario_id", sa.String(length=64), nullable=False),
        sa.Column("neic_code", sa.String(length=4), nullable=False),
        sa.Column("code_level", sa.Integer(), nullable=False),
        sa.Column("neic_name", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("tier1", sa.String(length=255), nullable=False),
        sa.Column("tier2", sa.String(length=255), nullable=True),
        sa.Column("tier3", sa.String(length=255), nullable=True),
        sa.Column("tier4", sa.String(length=255), nullable=True),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "code_level IN (2, 4)",
            name="ck_five_articles_mapping_rows_code_level",
        ),
        sa.CheckConstraint(
            "char_length(neic_code) = code_level",
            name="ck_five_articles_mapping_rows_code_length",
        ),
        sa.ForeignKeyConstraint(
            ["mapping_version_id"],
            ["five_articles_mapping_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_five_articles_mapping_rows_lookup",
        "five_articles_mapping_rows",
        ["mapping_version_id", "scenario_id", "code_level", "neic_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_five_articles_mapping_rows_lookup",
        table_name="five_articles_mapping_rows",
    )
    op.drop_table("five_articles_mapping_rows")
    op.drop_index(
        "ix_five_articles_mapping_versions_scenario_status",
        table_name="five_articles_mapping_versions",
    )
    op.drop_table("five_articles_mapping_versions")
