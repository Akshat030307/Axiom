"""Add research_runs.highlight_enabled

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-12

Per-run toggle (set at submission time, alongside mode) for synthesizer.py's
key-sentence highlighting. Defaults true so existing behavior is unchanged
for anyone not using the new toggle.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "research_runs",
        sa.Column("highlight_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("research_runs", "highlight_enabled")
