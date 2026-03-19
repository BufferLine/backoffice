from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Currency(Base):
    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    display_precision: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    storage_precision: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    is_crypto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    chain_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
