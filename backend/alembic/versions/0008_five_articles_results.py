"""Add versioned five-articles classification results."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0008_five_articles_results"
down_revision: Union[str, Sequence[str], None] = "0007_five_articles_mapping"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "five_articles_results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("scenario_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stage_a_result_id", sa.BigInteger(), nullable=False),
        sa.Column("mapping_version_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "labels",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("loan_neic_code", sa.String(length=4), nullable=True),
        sa.Column("loan_neic_name", sa.String(length=255), nullable=True),
        sa.Column("enterprise_neic_code", sa.String(length=4), nullable=True),
        sa.Column("enterprise_neic_name", sa.String(length=255), nullable=True),
        sa.Column("consistency_status", sa.String(length=32), nullable=True),
        sa.Column("consistency_basis", sa.Text(), nullable=True),
        sa.Column(
            "consistency_evidence_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "model_output",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('completed', 'not_applicable', 'needs_review', "
            "'classification_failed')",
            name="ck_five_articles_results_status",
        ),
        sa.CheckConstraint(
            "consistency_status IN ('consistent', 'inconsistent', "
            "'needs_review', 'not_applicable')",
            name="ck_five_articles_results_consistency_status",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["national_economy_classification_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stage_a_result_id"],
            ["national_economy_classification_results.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["mapping_version_id"],
            ["five_articles_mapping_versions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "case_id",
            "version",
            name="uq_five_articles_results_case_version",
        ),
    )
    op.create_index(
        "uq_five_articles_results_case_stage_a_completed",
        "five_articles_results",
        ["case_id", "stage_a_result_id"],
        unique=True,
        postgresql_where=sa.text("status = 'completed'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_five_articles_results_case_stage_a_completed",
        table_name="five_articles_results",
    )
    op.drop_table("five_articles_results")
