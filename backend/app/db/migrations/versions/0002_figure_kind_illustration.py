"""Add "illustration" to figures.kind's allowed values

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-10

Figure.kind (app/models/schemas.py) was widened to include "illustration"
for the new image_generator node, but the DB-level CHECK constraint from
0001_initial_schema.py was raw SQL (`kind IN ('chart','diagram',
'source_image')`), not something SQLAlchemy's ORM model declaration alone
would catch — this migration is the fix, found by an INSERT actually
failing against the real constraint, not by inspection.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE figures DROP CONSTRAINT figures_kind_check")
    op.execute(
        "ALTER TABLE figures ADD CONSTRAINT figures_kind_check "
        "CHECK (kind IN ('chart','diagram','source_image','illustration'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE figures DROP CONSTRAINT figures_kind_check")
    op.execute(
        "ALTER TABLE figures ADD CONSTRAINT figures_kind_check "
        "CHECK (kind IN ('chart','diagram','source_image'))"
    )
