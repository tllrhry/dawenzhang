"""Distinguish high-tech and specialized-innovation registries.

Revision ID: 0016_tech_registry_types
Revises: 0015_five_articles_policy
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016_tech_registry_types"
down_revision: Union[str, Sequence[str], None] = "0015_five_articles_policy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "technology_finance_ip_registry_versions",
        sa.Column("registry_type", sa.String(length=32), nullable=True),
    )
    op.execute(
        """
        UPDATE technology_finance_ip_registry_versions
        SET registry_type = CASE
            WHEN source_path LIKE '%高新技术%' AND source_path LIKE '%专精特新%'
                THEN 'legacy_combined'
            WHEN source_path LIKE '%专精特新%'
                THEN 'specialized_innovation'
            ELSE 'high_tech'
        END
        """
    )
    op.alter_column(
        "technology_finance_ip_registry_versions",
        "registry_type",
        existing_type=sa.String(length=32),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_technology_finance_ip_registry_versions_registry_type",
        "technology_finance_ip_registry_versions",
        "registry_type IN ('high_tech', 'specialized_innovation', 'legacy_combined')",
    )
    op.create_index(
        "ix_tech_fin_registry_type_version",
        "technology_finance_ip_registry_versions",
        ["registry_type", "version"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tech_fin_registry_type_version",
        table_name="technology_finance_ip_registry_versions",
    )
    op.drop_constraint(
        "ck_technology_finance_ip_registry_versions_registry_type",
        "technology_finance_ip_registry_versions",
        type_="check",
    )
    op.drop_column("technology_finance_ip_registry_versions", "registry_type")
