"""Initial empty schema for the application foundation.

Business tables will be introduced by later changes. Keeping this revision
explicit gives deployments a stable Alembic starting point.
"""

from typing import Sequence, Union


revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

