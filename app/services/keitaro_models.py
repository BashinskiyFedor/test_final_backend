"""Типизированные срезы ответов Keitaro Admin API (только нужные нам поля)."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EntityState(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    DELETED = "deleted"


class StreamType(StrEnum):
    REGULAR = "regular"


class StreamSchema(StrEnum):
    LANDINGS = "landings"


class ActionType(StrEnum):
    HTTP = "http"


class CampaignType(StrEnum):
    POSITION = "position"


class _Remote(BaseModel):
    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data: Any) -> Any:
        # Keitaro отдаёт null вместо отсутствующих значений — используем наши значения по умолчанию.
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


class RemoteOffer(_Remote):
    id: int
    name: str
    state: str = EntityState.ACTIVE


class RemoteStreamOffer(_Remote):
    offer_id: int
    share: int = 0
    state: str = EntityState.ACTIVE


class RemoteStream(_Remote):
    id: int
    name: str | None = None
    type: str = StreamType.REGULAR
    state: str = EntityState.ACTIVE
    offers: list[RemoteStreamOffer] = Field(default_factory=list)


class RemoteCampaign(_Remote):
    id: int
    name: str = ""
    alias: str | None = None
    state: str = EntityState.ACTIVE
