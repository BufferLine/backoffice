import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_payments_idempotency_key"),
        # Partial unique index: tx_hash UNIQUE WHERE tx_hash IS NOT NULL
        Index(
            "uq_payments_tx_hash_not_null",
            "tx_hash",
            unique=True,
            postgresql_where="tx_hash IS NOT NULL",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    related_entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    related_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(
        String(10), ForeignKey("currencies.code", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False)
    fx_rate_to_sgd: Mapped[float | None] = mapped_column(Numeric(19, 10), nullable=True)
    fx_rate_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    fx_rate_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sgd_value: Mapped[float | None] = mapped_column(Numeric(19, 6), nullable=True)
    tx_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chain_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bank_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proof_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    currency_rel = relationship("Currency", foreign_keys=[currency])
    proof_file = relationship("File", foreign_keys=[proof_file_id])
    creator = relationship("User", foreign_keys=[created_by])
