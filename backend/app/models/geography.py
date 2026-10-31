from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import CHAR, DateTime, ForeignKey, Index, SmallInteger, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, pg_enum, pk
from app.models.enums import RegionLevel, RegionStatus


class Country(Base):
    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    iso2: Mapped[str] = mapped_column(CHAR(2), unique=True)
    iso3: Mapped[str | None] = mapped_column(CHAR(3), unique=True)
    name: Mapped[str] = mapped_column(Text)
    default_currency: Mapped[str] = mapped_column(CHAR(3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class City(TimestampMixin, Base):
    __tablename__ = "cities"
    __table_args__ = (UniqueConstraint("country_id", "admin1_code", "name"),)

    id: Mapped[int] = pk()
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), index=True)
    admin1_code: Mapped[str | None] = mapped_column(Text)  # state / province / county
    admin1_name: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    external_ids: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)
    centroid = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    boundary_source: Mapped[str | None] = mapped_column(Text)
    status: Mapped[RegionStatus] = mapped_column(
        pg_enum(RegionStatus, "region_status"), server_default=RegionStatus.NOT_STARTED
    )


class Region(TimestampMixin, Base):
    __tablename__ = "regions"
    __table_args__ = (Index("ix_regions_city_level", "city_id", "level"),)

    id: Mapped[int] = pk()
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), index=True)
    level: Mapped[RegionLevel] = mapped_column(pg_enum(RegionLevel, "region_level"))
    name: Mapped[str] = mapped_column(Text)
    external_ids: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    # How each source identifies this region, e.g. {"ie_ppr": "Dublin 8"}
    source_location_ids: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)
    centroid = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    boundary_source: Mapped[str | None] = mapped_column(Text)
    # Derived from search_coverage by the coverage service; never set by hand.
    status: Mapped[RegionStatus] = mapped_column(
        pg_enum(RegionStatus, "region_status"), server_default=RegionStatus.NOT_STARTED
    )
    last_searched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    listings_found: Mapped[int] = mapped_column(server_default="0")
    listings_new: Mapped[int] = mapped_column(server_default="0")
    duplicates: Mapped[int] = mapped_column(server_default="0")
    errors: Mapped[int] = mapped_column(server_default="0")
