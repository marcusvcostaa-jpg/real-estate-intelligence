"""region neighbors tolerant to generalised boundaries

Generalised official boundaries (Tailte Éireann, 20 m) overlap slightly or leave slivers, so
ST_Touches missed real neighbours (County Dublin only "touched" Wicklow). Neighbours are now
regions of the same level and depth whose polygons lie within ~100 m (0.001 degrees).

Revision ID: e33a05b08bc5
Revises: 1e8e9dae7156
Create Date: 2026-11-01 13:32:42.456467

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e33a05b08bc5"
down_revision: str | Sequence[str] | None = "1e8e9dae7156"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_VIEW = """
CREATE MATERIALIZED VIEW region_neighbors AS
SELECT a.id AS region_id, b.id AS neighbor_id,
       CASE WHEN a.geom IS NOT NULL AND b.geom IS NOT NULL THEN 'TOUCHES' ELSE 'NEAR' END
         AS relation
FROM regions a
JOIN regions b
  ON a.id <> b.id
 AND a.level = b.level
 AND (a.parent_id IS NULL) = (b.parent_id IS NULL)
WHERE (a.geom IS NOT NULL AND b.geom IS NOT NULL
       -- 0.001 degrees ~ 70-110 m in Ireland; planar test uses the GIST index and covers
       -- overlaps (distance 0). Geography distance on county polygons took minutes.
       -- ponytail: refresh ~50 s (only after boundary imports); ST_Subdivide if it grows.
       AND ST_DWithin(a.geom, b.geom, 0.001))
   OR ((a.geom IS NULL OR b.geom IS NULL)
       AND ST_DWithin(a.centroid::geography, b.centroid::geography, 1500))
"""

OLD_VIEW = """
CREATE MATERIALIZED VIEW region_neighbors AS
SELECT a.id AS region_id, b.id AS neighbor_id,
       CASE WHEN a.geom IS NOT NULL AND b.geom IS NOT NULL THEN 'TOUCHES' ELSE 'NEAR' END
         AS relation
FROM regions a
JOIN regions b ON a.id <> b.id
WHERE (a.geom IS NOT NULL AND b.geom IS NOT NULL AND ST_Touches(a.geom, b.geom))
   OR ((a.geom IS NULL OR b.geom IS NULL)
       AND ST_DWithin(a.centroid::geography, b.centroid::geography, 1500))
"""

UNIQUE_INDEX = (
    "CREATE UNIQUE INDEX uq_region_neighbors ON region_neighbors (region_id, neighbor_id)"
)


def upgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW region_neighbors")
    op.execute(NEW_VIEW)
    op.execute(UNIQUE_INDEX)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW region_neighbors")
    op.execute(OLD_VIEW)
    op.execute(UNIQUE_INDEX)
