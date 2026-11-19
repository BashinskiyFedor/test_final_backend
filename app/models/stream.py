from typing import Self

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.services.keitaro_models import StreamType


class Stream(Base):
    """Поток (flow) Keitaro, подтянутый в нашу обёртку."""

    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    keitaro_stream_id: Mapped[int] = mapped_column(unique=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(32), default=StreamType.REGULAR)
    position: Mapped[int] = mapped_column(default=0)

    offers: Mapped[list["StreamOffer"]] = relationship(
        back_populates="stream",
        cascade="all, delete-orphan",
        order_by="StreamOffer.id",
        lazy="raise",
    )

    @property
    def has_offers(self) -> bool:
        return bool(self.offers)

    @property
    def dirty(self) -> bool:
        """Есть неопубликованные изменения."""
        return any(not o.is_clean for o in self.offers)

    @property
    def active_offers(self) -> list["StreamOffer"]:
        return [o for o in self.offers if o.active]

    def find_offer(self, offer_id: int) -> "StreamOffer | None":
        return next((o for o in self.offers if o.offer_id == offer_id), None)


class StreamOffer(Base):
    """Оффер потока в нашей обёртке: желаемое состояние (черновик) + последнее известное состояние Keitaro.

    - желаемое: ``active`` и ``share`` (то, что уйдёт в Keitaro при push);
    - Keitaro:  ``in_keitaro`` и ``published_share`` (то, что там сейчас).
    Поток «жёлтый» (есть неопубликованные изменения), если желаемое != Keitaro.
    ``active=False`` и ``in_keitaro=False`` — оффер в архиве (серый), его можно вернуть.
    """

    __tablename__ = "stream_offers"
    __table_args__ = (UniqueConstraint("stream_id", "offer_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"), index=True)
    offer_id: Mapped[int]
    name: Mapped[str] = mapped_column(String(255))

    active: Mapped[bool] = mapped_column(default=True)
    share: Mapped[int] = mapped_column(default=0)
    pinned: Mapped[bool] = mapped_column(default=False)

    in_keitaro: Mapped[bool] = mapped_column(default=False)
    published_share: Mapped[int] = mapped_column(default=0)
    # Хотя бы раз был опубликован в Keitaro: отличает «добавлен черновиком» от «вернули из архива».
    was_published: Mapped[bool] = mapped_column(default=False)

    stream: Mapped[Stream] = relationship(back_populates="offers", lazy="raise")

    # ---- конструкторы ----

    @classmethod
    def draft(cls, offer_id: int, name: str) -> Self:
        """Новый оффер, добавленный черновиком (в Keitaro ещё нет)."""
        return cls(
            offer_id=offer_id, name=name, active=True, share=0, pinned=False,
            in_keitaro=False, published_share=0, was_published=False,
        )  # fmt: skip

    @classmethod
    def from_keitaro(cls, offer_id: int, name: str, share: int) -> Self:
        """Оффер, который мы впервые увидели в Keitaro."""
        return cls(
            offer_id=offer_id, name=name, active=True, share=share, pinned=False,
            in_keitaro=True, published_share=share, was_published=True,
        )  # fmt: skip

    # ---- состояние ----

    @property
    def is_clean(self) -> bool:
        """Желаемое состояние совпадает с Keitaro."""
        if self.active != self.in_keitaro:
            return False
        return not self.active or self.share == self.published_share

    @property
    def is_new(self) -> bool:
        """Добавлен черновиком и ещё ни разу не публиковался."""
        return self.active and not self.in_keitaro and not self.was_published

    # ---- переходы ----

    def deactivate(self) -> None:
        self.active = False
        self.share = 0
        self.pinned = False

    def activate(self) -> None:
        self.active = True

    def apply_keitaro_state(self, share: int, name: str) -> None:
        """Офер найден в Keitaro при синхронизации; локальный черновик не затираем."""
        was_clean = self.is_clean
        self.name = name
        self.in_keitaro = True
        self.was_published = True
        self.published_share = share
        if was_clean:
            self.active = True
            self.share = share

    def mark_missing_in_keitaro(self) -> None:
        """Оффера больше нет в Keitaro: публикованный уходит в архив, наш черновик остаётся."""
        self.in_keitaro = False
        self.published_share = 0
        if self.was_published:
            self.deactivate()

    def revert_to_keitaro(self) -> bool:
        """Cancel. Возвращает False, если оффер надо удалить из нашей базы (черновик)."""
        if self.in_keitaro:
            self.active = True
            self.share = self.published_share
        elif self.was_published:  # вернули из архива и передумали — обратно в архив
            self.deactivate()
        else:
            return False
        return True

    def mark_pushed(self) -> None:
        self.in_keitaro = self.active
        self.published_share = self.share if self.active else 0
        if self.active:
            self.was_published = True
