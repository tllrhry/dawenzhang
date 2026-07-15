"""Add the versioned technology-finance IP enterprise registry."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_tech_finance_ip_registry"
down_revision: Union[str, Sequence[str], None] = "0013_green_condition_mapping"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "technology_finance_ip_registry_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('published')", name="ck_technology_finance_ip_registry_versions_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version", name="uq_technology_finance_ip_registry_versions_version"),
    )
    op.create_table(
        "technology_finance_ip_registry_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("version_id", sa.BigInteger(), nullable=False),
        sa.Column("enterprise_name", sa.Text(), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"], ["technology_finance_ip_registry_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "version_id", "enterprise_name",
            name="uq_technology_finance_ip_registry_entries_version_name",
        ),
    )


def downgrade() -> None:
    op.drop_table("technology_finance_ip_registry_entries")
    op.drop_table("technology_finance_ip_registry_versions")
