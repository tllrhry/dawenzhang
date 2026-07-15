"""Add condition-criteria storage for five-articles mapping rows.

Revision ID: 0013_green_condition_mapping
Revises: 0012_agriculture_related_results
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from app.core.config import get_settings


revision: str = "0013_green_condition_mapping"
down_revision: Union[str, Sequence[str], None] = "0012_agriculture_related_results"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CODE_LEVEL_CONSTRAINT = (
    "(neic_code = '-' AND code_level IS NULL) OR "
    "(neic_code <> '-' AND code_level IS NOT NULL "
    "AND code_level IN (2, 3, 4))"
)
_CODE_LENGTH_CONSTRAINT = (
    "(neic_code = '-' AND code_level IS NULL) OR "
    "(neic_code <> '-' AND code_level IS NOT NULL "
    "AND char_length(neic_code) = code_level)"
)


def upgrade() -> None:
    settings = get_settings()
    op.add_column(
        "five_articles_mapping_rows",
        sa.Column("condition_criteria", sa.Text(), nullable=True),
    )
    op.add_column(
        "five_articles_mapping_rows",
        sa.Column(
            "condition_embedding", Vector(settings.embedding_dimension), nullable=True
        ),
    )
    op.alter_column("five_articles_mapping_rows", "code_level", nullable=True)
    op.drop_constraint(
        "ck_five_articles_mapping_rows_code_level",
        "five_articles_mapping_rows",
        type_="check",
    )
    op.drop_constraint(
        "ck_five_articles_mapping_rows_code_length",
        "five_articles_mapping_rows",
        type_="check",
    )
    op.create_check_constraint(
        "ck_five_articles_mapping_rows_code_level",
        "five_articles_mapping_rows",
        _CODE_LEVEL_CONSTRAINT,
    )
    op.create_check_constraint(
        "ck_five_articles_mapping_rows_code_length",
        "five_articles_mapping_rows",
        _CODE_LENGTH_CONSTRAINT,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_five_articles_mapping_rows_code_length",
        "five_articles_mapping_rows",
        type_="check",
    )
    op.drop_constraint(
        "ck_five_articles_mapping_rows_code_level",
        "five_articles_mapping_rows",
        type_="check",
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM five_articles_mapping_rows
                WHERE neic_code = '-' AND code_level IS NULL
            ) THEN
                RAISE EXCEPTION
                    'cannot downgrade while placeholder NEIC mapping rows exist';
            END IF;
        END $$;
        """
    )
    op.alter_column("five_articles_mapping_rows", "code_level", nullable=False)
    op.create_check_constraint(
        "ck_five_articles_mapping_rows_code_level",
        "five_articles_mapping_rows",
        "code_level IN (2, 3, 4)",
    )
    op.create_check_constraint(
        "ck_five_articles_mapping_rows_code_length",
        "five_articles_mapping_rows",
        "char_length(neic_code) = code_level",
    )
    op.drop_column("five_articles_mapping_rows", "condition_embedding")
    op.drop_column("five_articles_mapping_rows", "condition_criteria")
