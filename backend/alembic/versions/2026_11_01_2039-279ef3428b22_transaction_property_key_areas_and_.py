"""transaction property key, areas and category

Revision ID: 279ef3428b22
Revises: f5c5a72e597a
Create Date: 2026-11-01 20:39:20.163808

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "279ef3428b22"
down_revision: str | Sequence[str] | None = "f5c5a72e597a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("property_transactions", sa.Column("source_property_key", sa.Text()))
    op.add_column("property_transactions", sa.Column("built_area_m2", sa.Numeric(10, 2)))
    op.add_column("property_transactions", sa.Column("land_area_m2", sa.Numeric(10, 2)))
    op.add_column("property_transactions", sa.Column("property_type", sa.Text()))
    op.add_column("property_transactions", sa.Column("category", sa.Text()))
    # The Irish register covers residential sales only (docs/DATA_SOURCES.md).
    op.execute(
        "UPDATE property_transactions SET category = 'RESIDENTIAL' "
        "WHERE source_id IN (SELECT id FROM sources WHERE code = 'ie_ppr')"
    )


def downgrade() -> None:
    op.drop_column("property_transactions", "category")
    op.drop_column("property_transactions", "property_type")
    op.drop_column("property_transactions", "land_area_m2")
    op.drop_column("property_transactions", "built_area_m2")
    op.drop_column("property_transactions", "source_property_key")
