"""Initial schema foundation: enable the pgvector extension.

Business tables are introduced by later changes. This revision only enables the
`vector` extension so subsequent migrations can declare pgvector columns, and
gives deployments a stable Alembic starting point on PostgreSQL.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Keep the extension in place on downgrade; other objects may depend on it.
    pass
