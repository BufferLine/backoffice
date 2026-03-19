import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class RecurringInvoiceRule(Base):
    __tablename__ = "recurring_invoice_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    day_of_month: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(10), ForeignKey("currencies.code", ondelete="RESTRICT"), nullable=False
    )
    line_items_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_issued_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL", use_alter=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    client = relationship("Client", foreign_keys=[client_id])
    currency_rel = relationship("Currency", foreign_keys=[currency])
    last_issued_invoice = relationship("Invoice", foreign_keys=[last_issued_invoice_id])


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("invoice_number", name="uq_invoices_invoice_number"),
        UniqueConstraint("idempotency_key", name="uq_invoices_idempotency_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(
        String(10), ForeignKey("currencies.code", ondelete="RESTRICT"), nullable=False
    )
    subtotal_amount: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    tax_rate: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    tax_amount: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wallet_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issued_pdf_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL"), nullable=True
    )
    recurring_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recurring_invoice_rules.id", ondelete="SET NULL", use_alter=True), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    client = relationship("Client", back_populates="invoices", foreign_keys=[client_id])
    currency_rel = relationship("Currency", foreign_keys=[currency])
    issued_pdf_file = relationship("File", foreign_keys=[issued_pdf_file_id])
    recurring_rule = relationship(
        "RecurringInvoiceRule", foreign_keys=[recurring_rule_id], back_populates=None
    )
    creator = relationship("User", foreign_keys=[created_by])
    line_items: Mapped[list["InvoiceLineItem"]] = relationship(
        "InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    amount: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="line_items")
