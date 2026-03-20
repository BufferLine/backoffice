import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class IntegrationEvent(Base):
    """Log of all inbound webhook events and outbound sync events."""

    __tablename__ = "integration_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_integration_events_provider_event"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # "inbound" | "outbound"
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="processing")
    # status values: processing | processed | failed | rejected | duplicate
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class IntegrationSyncState(Base):
    """Tracks sync progress per provider per capability (and optionally per account)."""

    __tablename__ = "integration_sync_states"
    __table_args__ = (
        UniqueConstraint(
            "provider", "capability", "account_id",
            name="uq_integration_sync_states_provider_cap_account",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    capability: Mapped[str] = mapped_column(String(50), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_cursor: Mapped[str | None] = mapped_column(String(500), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class IntegrationConfig(Base):
    """Runtime config for dynamic integration values (OAuth tokens, tenant IDs, etc.).

    Note: v1 stores values as plaintext. Encryption at rest is a planned follow-up.
    """

    __tablename__ = "integration_configs"
    __table_args__ = (
        UniqueConstraint("provider", "config_key", name="uq_integration_configs_provider_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    config_key: Mapped[str] = mapped_column(String(100), nullable=False)
    config_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
