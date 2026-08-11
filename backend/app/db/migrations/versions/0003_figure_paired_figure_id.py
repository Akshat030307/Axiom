"""Add figures.paired_figure_id

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-11

Links a real web photo (kind="source_image", fetched via Tavily image
search) to the AI illustration it accompanies. Nullable — only companion
source_image rows set it; every other figure (chart, diagram, illustration,
and any standalone source_image) leaves it null. Self-referential FK with
SET NULL on delete so removing the illustration doesn't cascade-delete its
still-valid companion photo.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "figures",
        sa.Column("paired_figure_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "figures_paired_figure_id_fkey",
        "figures",
        "figures",
        ["paired_figure_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("figures_paired_figure_id_fkey", "figures", type_="foreignkey")
    op.drop_column("figures", "paired_figure_id")
