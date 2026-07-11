"""Add auditable major-category hierarchy to industry chunks."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_catalog_hierarchy"
down_revision: Union[str, Sequence[str], None] = "0003_classification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "national_economy_industry_chunks",
        sa.Column("major_category_code", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "national_economy_industry_chunks",
        sa.Column("major_category_name", sa.String(length=255), nullable=True),
    )
    op.create_index(
        op.f("ix_national_economy_industry_chunks_major_category_code"),
        "national_economy_industry_chunks",
        ["major_category_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_national_economy_industry_chunks_major_category_code"),
        table_name="national_economy_industry_chunks",
    )
    op.drop_column("national_economy_industry_chunks", "major_category_name")
    op.drop_column("national_economy_industry_chunks", "major_category_code")
