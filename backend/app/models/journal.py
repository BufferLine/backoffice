import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    lines: Mapped[list["JournalLine"]] = relationship(
        "JournalLine", back_populates="journal_entry", cascade="all, delete-orphan", lazy="selectin"
    )
    confirmer = relationship("User", foreign_keys=[confirmed_by])
    creator = relationship("User", foreign_keys=[created_by])


class JournalLine(Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        CheckConstraint(
            "(debit > 0 AND credit = 0) OR (debit = 0 AND credit > 0)",
            name="chk_debit_or_credit",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    debit: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    credit: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code", ondelete="RESTRICT"), nullable=False
    )
    fx_rate_to_sgd: Mapped[float | None] = mapped_column(Numeric(19, 6), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    journal_entry: Mapped["JournalEntry"] = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account", foreign_keys=[account_id])
    currency_rel = relationship("Currency", foreign_keys=[currency])
