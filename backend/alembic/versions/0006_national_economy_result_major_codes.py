"""Add major-category codes to national economy classification results."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_result_major_codes"
down_revision: Union[str, Sequence[str], None] = "0005_loan_direction"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "national_economy_classification_results",
        sa.Column("industry_major_code", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "national_economy_classification_results",
        sa.Column("loan_industry_major_code", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column(
        "national_economy_classification_results", "loan_industry_major_code"
    )
    op.drop_column("national_economy_classification_results", "industry_major_code")
