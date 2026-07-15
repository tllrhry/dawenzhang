"""Version five-articles decisions by mapping and decision policy.

Revision ID: 0015_five_articles_policy
Revises: 0014_tech_finance_ip_registry
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015_five_articles_policy"
down_revision: Union[str, Sequence[str], None] = "0014_tech_finance_ip_registry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "five_articles_results",
        sa.Column(
            "decision_policy_version",
            sa.String(length=64),
            server_default=sa.text("'legacy-v1'"),
            nullable=False,
        ),
    )
    op.drop_index(
        "uq_five_articles_results_case_stage_a_completed",
        table_name="five_articles_results",
    )
    op.create_index(
        "uq_five_articles_results_case_stage_a_completed",
        "five_articles_results",
        [
            "case_id",
            "stage_a_result_id",
            "mapping_version_id",
            "decision_policy_version",
        ],
        unique=True,
        postgresql_where=sa.text("status = 'completed'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_five_articles_results_case_stage_a_completed",
        table_name="five_articles_results",
    )
    op.create_index(
        "uq_five_articles_results_case_stage_a_completed",
        "five_articles_results",
        ["case_id", "stage_a_result_id"],
        unique=True,
        postgresql_where=sa.text("status = 'completed'"),
    )
    op.drop_column("five_articles_results", "decision_policy_version")
