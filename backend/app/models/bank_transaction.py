import uuid
from datetime import datetime

from sqlalchemy import Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    __table_args__ = (
        UniqueConstraint("source", "source_tx_id", name="uq_bank_transactions_source_tx"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_tx_id: Mapped[str] = mapped_column(String(255), nullable=False)
    tx_date: Mapped[object] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(10), ForeignKey("currencies.code", ondelete="RESTRICT"), nullable=False
    )
    counterparty: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="SET NULL"), nullable=True
    )
    match_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unmatched")
    match_confidence: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    raw_data_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    statement_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL"), nullable=True
    )
    imported_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.now())
    imported_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    currency_rel = relationship("Currency", foreign_keys=[currency])
    matched_payment = relationship("Payment", foreign_keys=[matched_payment_id])
    statement_file = relationship("File", foreign_keys=[statement_file_id])
    importer = relationship("User", foreign_keys=[imported_by])
