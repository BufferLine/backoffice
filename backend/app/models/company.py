import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CompanySettings(Base):
    __tablename__ = "company_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uen: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_swift_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    logo_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL"), nullable=True
    )
    default_currency: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("currencies.code", ondelete="SET NULL"), nullable=True
    )
    default_payment_terms_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    gst_registered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gst_rate: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(20), nullable=True, default="SG")
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    logo_file = relationship("File", foreign_keys=[logo_file_id])
    currency = relationship("Currency", foreign_keys=[default_currency])
