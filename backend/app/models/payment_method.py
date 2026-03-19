import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(10), ForeignKey("currencies.code", ondelete="RESTRICT"), nullable=False
    )
    bank_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_swift_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    wallet_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chain_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    uen_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    currency_rel = relationship("Currency", foreign_keys=[currency])
    creator = relationship("User", foreign_keys=[created_by])
