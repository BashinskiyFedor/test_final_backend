from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

STATUS_PENDING = "pending"  # строка зарезервирована, в Keitaro ещё не подтверждено
STATUS_CREATED = "created"  # кампания и flow есть в Keitaro, ID сохранены


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Детерминированный ключ идемпотентности (имя + гео + оффер); уникален и у нас, и в Keitaro.
    alias: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(16), default=STATUS_PENDING, index=True)
    keitaro_campaign_id: Mapped[int | None] = mapped_column(index=True, default=None)
    keitaro_stream_id: Mapped[int | None] = mapped_column(default=None)
    name: Mapped[str] = mapped_column(String(255))
    country: Mapped[str] = mapped_column(String(2))
    offer_id: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
