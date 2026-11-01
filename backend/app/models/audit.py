from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, pg_enum, pk
from app.models.enums import UserRole


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = pk()
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, "user_role"), server_default=UserRole.VIEWER
    )
    is_active: Mapped[bool] = mapped_column(server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DataQualityIssue(Base):
    __tablename__ = "data_quality"
    __table_args__ = (
        Index("ix_data_quality_entity", "entity_type", "entity_id"),
        Index(
            "ix_data_quality_open",
            "entity_type",
            "rule_code",
            postgresql_where=text("resolved_at IS NULL"),
        ),
        # One open issue per entity and rule, so validators can re-run safely.
        Index(
            "uq_data_quality_open_issue",
            "entity_type",
            "entity_id",
            "rule_code",
            unique=True,
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )

    id: Mapped[int] = pk()
    entity_type: Mapped[str] = mapped_column(Text)  # PROPERTY, LISTING, TRANSACTION
    entity_id: Mapped[int] = mapped_column(BigInteger)
    rule_code: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)  # INFO, WARNING, ERROR
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSONB)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)


class AgentExecution(Base):
    __tablename__ = "agent_executions"
    __table_args__ = (Index("ix_agent_executions_agent_started", "agent", "started_at"),)

    id: Mapped[int] = pk()
    agent: Mapped[str] = mapped_column(Text)
    task_id: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("search_jobs.id"), index=True)
    status: Mapped[str] = mapped_column(Text)
    input: Mapped[dict | None] = mapped_column(JSONB)
    output: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None]
    llm_model: Mapped[str | None] = mapped_column(Text)
    tokens_in: Mapped[int | None]
    tokens_out: Mapped[int | None]
    cost_estimate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
