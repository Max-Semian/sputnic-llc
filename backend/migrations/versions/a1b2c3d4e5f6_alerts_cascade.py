"""alerts cascade on file delete

Revision ID: a1b2c3d4e5f6
Revises: 0d6439d2e79f
Create Date: 2026-09-08 07:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "0d6439d2e79f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAME = "alerts_file_id_fkey"


def upgrade() -> None:
    """Recreate the alerts->files FK with ON DELETE CASCADE.

    Deleting a file now removes its alerts instead of failing with an
    IntegrityError (previously the API returned HTTP 500 after the physical
    file had already been removed from storage).
    """
    op.drop_constraint(FK_NAME, "alerts", type_="foreignkey")
    op.create_foreign_key(
        FK_NAME,
        "alerts",
        "files",
        ["file_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(FK_NAME, "alerts", type_="foreignkey")
    op.create_foreign_key(
        FK_NAME,
        "alerts",
        "files",
        ["file_id"],
        ["id"],
    )
