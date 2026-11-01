"""property sales summary and transactions region-date index

property_sales_summary: one row per property with its last sale and sale count, so the
property search can filter/sort 300k+ properties without a per-row subquery. Derived data,
refreshed after each deduplication (app/services/summary.py).

Revision ID: f5c5a72e597a
Revises: e33a05b08bc5
Create Date: 2026-11-01 18:14:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "f5c5a72e597a"
down_revision: str | Sequence[str] | None = "e33a05b08bc5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUMMARY_VIEW = """
CREATE MATERIALIZED VIEW property_sales_summary AS
SELECT p.id AS property_id, p.public_id, p.region_id, p.address_display, p.postal_code,
       s.sales, s.first_sale_date,
       l.transaction_date AS last_sale_date, l.price AS last_sale_price, l.currency,
       l.is_full_market_price AS last_full_market, l.vat_exclusive AS last_vat_exclusive,
       (l.description_original ILIKE 'New %' OR l.description_original ILIKE '%Nua%')
         AS last_is_new,
       l.source_id AS last_source_id
FROM properties p
JOIN (
    SELECT property_id, count(*) AS sales, min(transaction_date) AS first_sale_date
    FROM property_transactions WHERE property_id IS NOT NULL GROUP BY property_id
) s ON s.property_id = p.id
JOIN (
    SELECT DISTINCT ON (property_id) *
    FROM property_transactions WHERE property_id IS NOT NULL
    ORDER BY property_id, transaction_date DESC, id DESC
) l ON l.property_id = p.id
"""


def upgrade() -> None:
    op.create_index(
        "ix_property_transactions_region_date",
        "property_transactions",
        ["region_id", "transaction_date"],
    )
    op.execute(SUMMARY_VIEW)
    # Unique index allows REFRESH MATERIALIZED VIEW CONCURRENTLY (reads keep working).
    op.execute(
        "CREATE UNIQUE INDEX uq_property_sales_summary ON property_sales_summary (property_id)"
    )
    op.execute(
        "CREATE INDEX ix_property_sales_summary_region_last ON property_sales_summary "
        "(region_id, last_sale_date DESC, property_id DESC)"
    )
    op.execute(
        "CREATE INDEX ix_property_sales_summary_last ON property_sales_summary "
        "(last_sale_date DESC, property_id DESC)"
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW property_sales_summary")
    op.drop_index("ix_property_transactions_region_date", table_name="property_transactions")
