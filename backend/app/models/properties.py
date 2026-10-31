"""Physical properties vs. listings: a property can have many listings across sources.
Deduplication only links listings to properties; listings are never deleted."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from geoalchemy2 import Geography
from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, pg_enum, pk
from app.models.enums import (
    DedupDecision,
    ExtractionMethod,
    HistoryEvent,
    ListingStatus,
    OfferType,
    ValidationStatus,
)

Money = Numeric(14, 2)
Area = Numeric(10, 2)
Confidence = Numeric(4, 3)


class Property(TimestampMixin, Base):
    """Consolidated physical property. Provenance of each value lives in property_features."""

    __tablename__ = "properties"
    __table_args__ = (Index("ix_properties_city_type", "city_id", "property_type"),)

    id: Mapped[int] = pk()
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID, unique=True, server_default=text("gen_random_uuid()")
    )
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), index=True)
    city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id"), index=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), index=True)
    property_type: Mapped[str] = mapped_column(Text)  # APARTMENT, HOUSE, LAND, COMMERCIAL, ...
    category: Mapped[str] = mapped_column(Text)  # RESIDENTIAL, COMMERCIAL, LAND, OTHER
    # LISTED, NOT_LISTED, UNKNOWN. Never "SOLD" by inference.
    status: Mapped[str] = mapped_column(Text, server_default="UNKNOWN")
    address_display: Mapped[str | None] = mapped_column(Text)
    address_normalized: Mapped[str | None] = mapped_column(Text)
    unit_identifier: Mapped[str | None] = mapped_column(Text)  # apartment/unit number
    postal_code: Mapped[str | None] = mapped_column(Text, index=True)
    location = mapped_column(Geography("POINT", srid=4326), nullable=True)
    location_precision: Mapped[str | None] = mapped_column(Text)
    built_area_m2: Mapped[Decimal | None] = mapped_column(Area)
    land_area_m2: Mapped[Decimal | None] = mapped_column(Area)
    useful_area_m2: Mapped[Decimal | None] = mapped_column(Area)
    total_area_m2: Mapped[Decimal | None] = mapped_column(Area)
    bedrooms: Mapped[int | None] = mapped_column(SmallInteger)
    bathrooms: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    suites: Mapped[int | None] = mapped_column(SmallInteger)
    garage_spaces: Mapped[int | None] = mapped_column(SmallInteger)
    parking_spaces: Mapped[int | None] = mapped_column(SmallInteger)
    living_rooms: Mapped[int | None] = mapped_column(SmallInteger)
    kitchens: Mapped[int | None] = mapped_column(SmallInteger)
    has_garden: Mapped[bool | None]
    has_balcony: Mapped[bool | None]
    floors: Mapped[int | None] = mapped_column(SmallInteger)
    floor_level: Mapped[int | None] = mapped_column(SmallInteger)
    year_built: Mapped[int | None] = mapped_column(SmallInteger)
    energy_rating: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Confidence)
    validation_status: Mapped[ValidationStatus] = mapped_column(
        pg_enum(ValidationStatus, "validation_status"), server_default=ValidationStatus.PENDING
    )


class PropertyListing(TimestampMixin, Base):
    """A listing as published by one source. Original values are preserved."""

    __tablename__ = "property_listings"

    id: Mapped[int] = pk()
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    external_id: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    offer_type: Mapped[OfferType] = mapped_column(pg_enum(OfferType, "offer_type"))
    listing_status: Mapped[ListingStatus] = mapped_column(
        pg_enum(ListingStatus, "listing_status"), server_default=ListingStatus.ACTIVE
    )
    price_text_original: Mapped[str | None] = mapped_column(Text)
    price_original: Mapped[Decimal | None] = mapped_column(Money)
    currency: Mapped[str | None] = mapped_column(CHAR(3))
    rent_period: Mapped[str | None] = mapped_column(Text)  # MONTH, WEEK, ... (RENT only)
    price_monthly: Mapped[Decimal | None] = mapped_column(Money)
    price_per_m2: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    price_per_m2_basis: Mapped[str | None] = mapped_column(Text)  # BUILT | USEFUL | TOTAL
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_misses: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    raw_payload: Mapped[dict] = mapped_column(JSONB)
    raw_payload_sha256: Mapped[str] = mapped_column(CHAR(64))
    confidence: Mapped[Decimal | None] = mapped_column(Confidence)
    validation_status: Mapped[ValidationStatus] = mapped_column(
        pg_enum(ValidationStatus, "validation_status"), server_default=ValidationStatus.PENDING
    )
    last_job_id: Mapped[int | None] = mapped_column(ForeignKey("search_jobs.id"), index=True)

    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        CheckConstraint(
            "price_per_m2 IS NULL OR price_per_m2_basis IN ('BUILT','USEFUL','TOTAL')",
            name="price_per_m2_basis",
        ),
    )


class PropertyFeature(Base):
    """Field-level provenance: original value, normalized value, method, evidence."""

    __tablename__ = "property_features"
    __table_args__ = (
        Index("ix_property_features_listing_field", "listing_id", "field_name"),
        Index("ix_property_features_property_field", "property_id", "field_name"),
        CheckConstraint("method <> 'LLM' OR evidence IS NOT NULL", name="llm_needs_evidence"),
        CheckConstraint("method <> 'ESTIMATE' OR is_estimated", name="estimate_flagged"),
    )

    id: Mapped[int] = pk()
    listing_id: Mapped[int] = mapped_column(ForeignKey("property_listings.id"))
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id"))
    field_name: Mapped[str] = mapped_column(Text)
    value_original: Mapped[str | None] = mapped_column(Text)
    unit_original: Mapped[str | None] = mapped_column(Text)
    value_normalized: Mapped[Decimal | None] = mapped_column(Numeric)
    value_text: Mapped[str | None] = mapped_column(Text)
    unit_normalized: Mapped[str | None] = mapped_column(Text)
    method: Mapped[ExtractionMethod] = mapped_column(pg_enum(ExtractionMethod, "extraction_method"))
    evidence: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal] = mapped_column(Confidence)
    is_estimated: Mapped[bool] = mapped_column(server_default="false")
    extractor_version: Mapped[str] = mapped_column(Text)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PropertyHistory(Base):
    __tablename__ = "property_history"
    __table_args__ = (
        Index("ix_property_history_property_observed", "property_id", "observed_at"),
        Index("ix_property_history_listing_observed", "listing_id", "observed_at"),
    )

    id: Mapped[int] = pk()
    listing_id: Mapped[int] = mapped_column(ForeignKey("property_listings.id"))
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id"))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    event: Mapped[HistoryEvent] = mapped_column(pg_enum(HistoryEvent, "history_event"))
    old_price: Mapped[Decimal | None] = mapped_column(Money)
    new_price: Mapped[Decimal | None] = mapped_column(Money)
    currency: Mapped[str | None] = mapped_column(CHAR(3))
    old_status: Mapped[ListingStatus | None] = mapped_column(
        pg_enum(ListingStatus, "listing_status")
    )
    new_status: Mapped[ListingStatus | None] = mapped_column(
        pg_enum(ListingStatus, "listing_status")
    )
    url: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    job_id: Mapped[int | None] = mapped_column(ForeignKey("search_jobs.id"), index=True)


class PropertyTransaction(Base):
    """Actually transacted price from an official register (not an asking price)."""

    __tablename__ = "property_transactions"
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)

    id: Mapped[int] = pk()
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    external_id: Mapped[str] = mapped_column(Text)  # source id or sha256 of normalized row
    transaction_date: Mapped[date] = mapped_column(Date)
    price: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(CHAR(3))
    is_full_market_price: Mapped[bool | None]
    vat_exclusive: Mapped[bool | None]
    address_original: Mapped[str | None] = mapped_column(Text)
    postal_code: Mapped[str | None] = mapped_column(Text)
    description_original: Mapped[str | None] = mapped_column(Text)
    location = mapped_column(Geography("POINT", srid=4326), nullable=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), index=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DedupCandidate(Base):
    __tablename__ = "dedup_candidates"
    __table_args__ = (UniqueConstraint("listing_id", "candidate_property_id"),)

    id: Mapped[int] = pk()
    listing_id: Mapped[int] = mapped_column(ForeignKey("property_listings.id"))
    candidate_property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    score: Mapped[Decimal] = mapped_column(Confidence)
    signals: Mapped[dict] = mapped_column(JSONB)
    vetoes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    decision: Mapped[DedupDecision] = mapped_column(
        pg_enum(DedupDecision, "dedup_decision"), server_default=DedupDecision.PENDING
    )
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
