from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text

from app.database.session import engine


@contextmanager
def advisory_lock(name: str) -> Iterator[bool]:
    """Non-blocking Postgres advisory lock held on its own connection, so it survives the
    commits of the work it protects. Yields False if someone else holds it."""
    with engine.connect() as conn:
        acquired = conn.scalar(text("SELECT pg_try_advisory_lock(hashtext(:k))"), {"k": name})
        try:
            yield bool(acquired)
        finally:
            if acquired:
                conn.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": name})
