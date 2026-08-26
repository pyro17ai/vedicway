"""Allow UUID-only public media for external distribution.

Revision ID: 20260819_01
Revises: 20260728_01
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260819_01"
down_revision: str | None = "20260728_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("media_assets") as batch:
        batch.add_column(
            sa.Column(
                "public_unlisted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("media_assets") as batch:
        batch.drop_column("public_unlisted")
