"""inclusive finance results

Revision ID: 0010_inclusive_finance_results
Revises: 0008_five_articles_results
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_inclusive_finance_results"
down_revision = "0008_five_articles_results"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("inclusive_finance_results",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.BigInteger(), sa.ForeignKey("national_economy_classification_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scenario_id", sa.String(64), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("status", sa.String(32), nullable=False),
        sa.Column("stage_a_result_id", sa.BigInteger(), sa.ForeignKey("national_economy_classification_results.id", ondelete="CASCADE"), nullable=False),
        sa.Column("borrower_type", sa.String(32)), sa.Column("computed_size", sa.String(16)), sa.Column("filled_size", sa.String(16)), sa.Column("size_consistent", sa.Boolean()), sa.Column("is_operating_loan", sa.Boolean()), sa.Column("credit_amount_wan", sa.Float()), sa.Column("qualifies", sa.Boolean()), sa.Column("inclusive_category", sa.String(64)), sa.Column("basis", sa.Text()),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("anomalies", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("determination", postgresql.JSONB()), sa.Column("error_detail", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("case_id", "version", name="uq_inclusive_finance_results_case_version"),
        sa.CheckConstraint("status IN ('completed', 'not_applicable', 'needs_review', 'classification_failed')", name="ck_inclusive_finance_results_status"),
        sa.CheckConstraint("borrower_type IS NULL OR borrower_type IN ('enterprise', 'individual_business', 'small_micro_owner', 'farmer')", name="ck_inclusive_finance_results_borrower_type"),
        sa.CheckConstraint("computed_size IS NULL OR computed_size IN ('大型', '中型', '小型', '微型', '不可判定')", name="ck_inclusive_finance_results_computed_size"),
    )
    op.create_index("uq_inclusive_finance_results_case_stage_a_completed", "inclusive_finance_results", ["case_id", "stage_a_result_id"], unique=True, postgresql_where=sa.text("status = 'completed'"))

def downgrade() -> None:
    op.drop_index("uq_inclusive_finance_results_case_stage_a_completed", table_name="inclusive_finance_results")
    op.drop_table("inclusive_finance_results")
