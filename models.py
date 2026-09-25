from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Trigger(Base):
    """
    A one-shot alert: "ping me when X happens." Unlike a continuous
    monitor, a Trigger fires exactly once — the moment its condition is
    met, it notifies and deactivates. It does not re-arm.

    Scheduling: the scheduler picks up any trigger where
    `active is True and next_check_at <= now()` — i.e. enough time
    (>= interval_seconds) has elapsed since the last check. This is the
    same condition as "last_checked_at + interval_seconds <= now",
    just stored as a precomputed `next_check_at` so the scheduler's query
    is a plain indexed comparison instead of arithmetic on every row.
    """

    __tablename__ = "triggers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))

    source: Mapped[str] = mapped_column(String(50))
    config: Mapped[dict] = mapped_column(JSON)
    condition: Mapped[dict] = mapped_column(JSON)  # {"field": ..., "operator": ..., "value": ...}
    notification: Mapped[dict] = mapped_column(JSON)  # {"channel": ...}

    interval_seconds: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_check_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DynamicConnectorConfig(Base):
    """
    Persisted config for a connector registered at runtime by the
    discovery agent (or manually), instead of a hand-written Python file.
    Reloaded into the registry as a DynamicConnector at startup, so
    "adding a new source" survives a restart without touching code.
    """

    __tablename__ = "dynamic_connectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    config: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
