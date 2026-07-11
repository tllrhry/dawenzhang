"""Add national economy classification cases and result history."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0003_classification"
down_revision: Union[str, Sequence[str], None] = "0002_national_economy_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "national_economy_classification_cases",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("scenario", sa.String(length=64), nullable=False),
        sa.Column("input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_national_economy_classification_cases_scenario"),
        "national_economy_classification_cases",
        ["scenario"],
        unique=False,
    )
    op.create_index(
        op.f("ix_national_economy_classification_cases_status"),
        "national_economy_classification_cases",
        ["status"],
        unique=False,
    )
    op.create_table(
        "national_economy_classification_results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("industry_code", sa.String(length=4), nullable=True),
        sa.Column("industry_name", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("candidate_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("objection", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["national_economy_classification_cases.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "case_id",
            "version",
            name="uq_national_economy_classification_result_case_version",
        ),
    )
    op.create_index(
        op.f("ix_national_economy_classification_results_case_id"),
        "national_economy_classification_results",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_national_economy_classification_results_status"),
        "national_economy_classification_results",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_national_economy_classification_results_status"),
        table_name="national_economy_classification_results",
    )
    op.drop_index(
        op.f("ix_national_economy_classification_results_case_id"),
        table_name="national_economy_classification_results",
    )
    op.drop_table("national_economy_classification_results")
    op.drop_index(
        op.f("ix_national_economy_classification_cases_status"),
        table_name="national_economy_classification_cases",
    )
    op.drop_index(
        op.f("ix_national_economy_classification_cases_scenario"),
        table_name="national_economy_classification_cases",
    )
    op.drop_table("national_economy_classification_cases")
