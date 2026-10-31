from logging.config import fileConfig

from geoalchemy2 import alembic_helpers
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (registers all tables)
from alembic import context
from app.core.config import get_settings
from app.database.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
# Tests point migrations at a separate database via -x url=...
database_url = context.get_x_argument(as_dictionary=True).get("url") or get_settings().database_url

# geoalchemy2 helpers: render spatial types/indexes and ignore PostGIS system tables.
_context_opts = dict(
    target_metadata=target_metadata,
    include_object=alembic_helpers.include_object,
    process_revision_directives=alembic_helpers.writer,
    render_item=alembic_helpers.render_item,
    compare_type=True,
)


def run_migrations_offline() -> None:
    context.configure(url=database_url, literal_binds=True, **_context_opts)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, **_context_opts)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
