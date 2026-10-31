from datetime import datetime, timedelta

from sqlalchemy import ARRAY, DateTime, ForeignKey, Interval, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, pg_enum, pk
from app.models.enums import IntegrationType, PermissionStatus, PermissionType, SourceStatus


class Source(TimestampMixin, Base):
    __tablename__ = "sources"

    id: Mapped[int] = pk()
    code: Mapped[str] = mapped_column(Text, unique=True)  # = connector module name
    name: Mapped[str] = mapped_column(Text)
    country_id: Mapped[int | None] = mapped_column(ForeignKey("countries.id"), index=True)
    base_url: Mapped[str] = mapped_column(Text)
    integration_type: Mapped[IntegrationType] = mapped_column(
        pg_enum(IntegrationType, "integration_type")
    )
    has_api: Mapped[bool] = mapped_column(server_default="false")
    rate_limit_per_minute: Mapped[int]
    daily_request_budget: Mapped[int | None]
    min_refresh_interval: Mapped[timedelta] = mapped_column(Interval)
    available_fields: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    status: Mapped[SourceStatus] = mapped_column(
        pg_enum(SourceStatus, "source_status"), server_default=SourceStatus.PENDING_APPROVAL
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class SourcePermission(Base):
    """Evidence that collecting from a source is allowed. Collector refuses jobs without an
    APPROVED, unexpired row."""

    __tablename__ = "source_permissions"

    id: Mapped[int] = pk()
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    permission_type: Mapped[PermissionType] = mapped_column(
        pg_enum(PermissionType, "permission_type")
    )
    status: Mapped[PermissionStatus] = mapped_column(
        pg_enum(PermissionStatus, "permission_status"), server_default=PermissionStatus.PENDING
    )
    license_name: Mapped[str | None] = mapped_column(Text)
    evidence_url: Mapped[str | None] = mapped_column(Text)
    evidence_document: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text)
    restrictions: Mapped[str | None] = mapped_column(Text)
    attribution_required: Mapped[bool] = mapped_column(server_default="false")
    attribution_text: Mapped[str | None] = mapped_column(Text)
    robots_txt_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
