"""empty message

Revision ID: 804ca5e5e950
Revises: c68c06239e08
Create Date: 2025-09-23 17:50:23.630496

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "804ca5e5e950"
down_revision: Union[str, Sequence[str], None] = "c68c06239e08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
