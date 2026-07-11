"""Add loan-direction fields to national economy classification results."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_loan_direction"
down_revision: Union[str, Sequence[str], None] = "0004_catalog_hierarchy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "national_economy_classification_results",
        sa.Column("loan_industry_code", sa.String(length=4), nullable=True),
    )
    op.add_column(
        "national_economy_classification_results",
        sa.Column("loan_industry_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "national_economy_classification_results",
        sa.Column("loan_matching_basis", sa.Text(), nullable=True),
    )
    op.add_column(
        "national_economy_classification_results",
        sa.Column("loan_matches_enterprise", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("national_economy_classification_results", "loan_matches_enterprise")
    op.drop_column("national_economy_classification_results", "loan_matching_basis")
    op.drop_column("national_economy_classification_results", "loan_industry_name")
    op.drop_column("national_economy_classification_results", "loan_industry_code")
