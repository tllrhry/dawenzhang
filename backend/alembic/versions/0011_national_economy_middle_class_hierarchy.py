"""Add V2 category and middle-class hierarchy metadata."""

from alembic import op
import sqlalchemy as sa


revision = "0011_middle_class_hierarchy"
down_revision = "0010_inclusive_finance_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("national_economy_industry_chunks", sa.Column("category_name", sa.String(length=255), nullable=True))
    op.add_column("national_economy_industry_chunks", sa.Column("middle_category_code", sa.String(length=16), nullable=True))
    op.add_column("national_economy_industry_chunks", sa.Column("middle_category_name", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_national_economy_industry_chunks_middle_category_code"), "national_economy_industry_chunks", ["middle_category_code"], unique=False)
    op.add_column("national_economy_classification_results", sa.Column("industry_middle_code", sa.String(length=16), nullable=True))
    op.add_column("national_economy_classification_results", sa.Column("industry_middle_name", sa.String(length=255), nullable=True))
    op.add_column("national_economy_classification_results", sa.Column("industry_category_name", sa.String(length=255), nullable=True))
    op.add_column("national_economy_classification_results", sa.Column("loan_industry_middle_code", sa.String(length=16), nullable=True))
    op.add_column("national_economy_classification_results", sa.Column("loan_industry_middle_name", sa.String(length=255), nullable=True))
    op.add_column("national_economy_classification_results", sa.Column("loan_industry_category_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("national_economy_classification_results", "loan_industry_category_name")
    op.drop_column("national_economy_classification_results", "loan_industry_middle_name")
    op.drop_column("national_economy_classification_results", "loan_industry_middle_code")
    op.drop_column("national_economy_classification_results", "industry_middle_name")
    op.drop_column("national_economy_classification_results", "industry_category_name")
    op.drop_column("national_economy_classification_results", "industry_middle_code")
    op.drop_index(op.f("ix_national_economy_industry_chunks_middle_category_code"), table_name="national_economy_industry_chunks")
    op.drop_column("national_economy_industry_chunks", "middle_category_name")
    op.drop_column("national_economy_industry_chunks", "middle_category_code")
    op.drop_column("national_economy_industry_chunks", "category_name")
