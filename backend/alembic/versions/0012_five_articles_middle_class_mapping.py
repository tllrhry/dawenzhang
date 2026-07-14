"""Allow three-digit five-articles mapping rows."""

from alembic import op
import sqlalchemy as sa


revision = "0012_five_middle"
down_revision = "0011_middle_class_hierarchy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_five_articles_mapping_rows_code_level",
        "five_articles_mapping_rows",
        type_="check",
    )
    op.create_check_constraint(
        "ck_five_articles_mapping_rows_code_level",
        "five_articles_mapping_rows",
        "code_level IN (2, 3, 4)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_five_articles_mapping_rows_code_level",
        "five_articles_mapping_rows",
        type_="check",
    )
    op.create_check_constraint(
        "ck_five_articles_mapping_rows_code_level",
        "five_articles_mapping_rows",
        "code_level IN (2, 4)",
    )
