"""Add "reference_diagram" to figures.kind's allowed values

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-13

Figure.kind (app/models/schemas.py) was widened to include
"reference_diagram" for image_generator's new behavior — finding a real
diagram via Wikimedia Commons search instead of generating an AI
illustration — but the DB-level CHECK constraint is raw SQL, not something
SQLAlchemy's ORM model declaration alone would catch. Same fix, same root
cause, as 0002_figure_kind_illustration.py.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE figures DROP CONSTRAINT figures_kind_check")
    op.execute(
        "ALTER TABLE figures ADD CONSTRAINT figures_kind_check "
        "CHECK (kind IN ('chart','diagram','source_image','illustration','reference_diagram'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE figures DROP CONSTRAINT figures_kind_check")
    op.execute(
        "ALTER TABLE figures ADD CONSTRAINT figures_kind_check "
        "CHECK (kind IN ('chart','diagram','source_image','illustration'))"
    )
