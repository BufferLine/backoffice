import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Loan(Base):
    """Shareholder loans, director loans, bank loans, etc."""

    __tablename__ = "loans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # loan_type: shareholder_loan, director_loan, bank_loan, intercompany_loan
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    # direction: inbound (we borrowed) / outbound (we lent)
    counterparty: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(10), ForeignKey("currencies.code", ondelete="RESTRICT"), nullable=False
    )
    principal: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False)
    interest_rate: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False, default=0)
    # interest_rate: annual rate as decimal (e.g., 0.05 = 5%)
    interest_type: Mapped[str] = mapped_column(String(20), nullable=False, default="simple")
    # interest_type: simple / compound
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # status: active / repaid / written_off
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL"), nullable=True
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    currency_rel = relationship("Currency", foreign_keys=[currency])
    document_file = relationship("File", foreign_keys=[document_file_id])
    creator = relationship("User", foreign_keys=[created_by])
