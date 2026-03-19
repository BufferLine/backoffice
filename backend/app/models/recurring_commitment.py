import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class RecurringCommitment(Base):
    __tablename__ = "recurring_commitments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL", use_alter=True, name="fk_recurring_commitments_account_id"), nullable=True
    )
    currency: Mapped[str] = mapped_column(
        String(10), ForeignKey("currencies.code", ondelete="RESTRICT"), nullable=False
    )
    expected_amount: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    day_of_period: Mapped[int | None] = mapped_column(nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL", use_alter=True, name="fk_recurring_commitments_last_transaction_id"), nullable=True
    )
    tolerance_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=10.00)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    account = relationship("Account", foreign_keys=[account_id])
    currency_rel = relationship("Currency", foreign_keys=[currency])
    creator = relationship("User", foreign_keys=[created_by])
    last_transaction = relationship("Transaction", foreign_keys=[last_transaction_id])
