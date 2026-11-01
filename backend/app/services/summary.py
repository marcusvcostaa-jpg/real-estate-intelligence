from sqlalchemy import text
from sqlalchemy.orm import Session


def refresh_property_summary(db: Session) -> None:
    """Rebuild property_sales_summary (derived from properties + transactions). CONCURRENTLY
    keeps the property search readable while it refreshes."""
    db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY property_sales_summary"))
    db.commit()
