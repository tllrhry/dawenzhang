"""add agriculture related stage B results

Revision ID: 0012_agriculture_related_results
Revises: 0012_five_middle
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0012_agriculture_related_results"
down_revision = "0012_five_middle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agriculture_related_results",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "case_id",
            sa.BigInteger(),
            sa.ForeignKey("national_economy_classification_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scenario_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "stage_a_result_id",
            sa.BigInteger(),
            sa.ForeignKey("national_economy_classification_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_agriculture_related", sa.Boolean()),
        sa.Column("matched_categories", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("basis", sa.Text()),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("model_output", postgresql.JSONB()),
        sa.Column("error_detail", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("case_id", "version", name="uq_agriculture_related_results_case_version"),
        sa.CheckConstraint(
            "status IN ('completed', 'not_applicable', 'needs_review', 'classification_failed')",
            name="ck_agriculture_related_results_status",
        ),
    )
    op.create_index(
        "uq_agriculture_related_results_case_stage_a_completed",
        "agriculture_related_results",
        ["case_id", "stage_a_result_id"],
        unique=True,
        postgresql_where=sa.text("status = 'completed'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_agriculture_related_results_case_stage_a_completed",
        table_name="agriculture_related_results",
    )
    op.drop_table("agriculture_related_results")
