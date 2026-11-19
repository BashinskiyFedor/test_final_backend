from datetime import datetime

from app.models import Campaign
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    country: str = Field(description="Гео-код страны, ISO 3166-1 alpha-2, например US")
    offer_id: int = Field(gt=0, description="ID оффера в Keitaro")

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Название не может быть пустым")
        return v

    @field_validator("country")
    @classmethod
    def normalize_country(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 2 or not v.isascii() or not v.isalpha():
            raise ValueError("Гео-код должен состоять из двух латинских букв, например US")
        return v


class CampaignRead(BaseModel):
    campaign_id: int
    stream_id: int
    name: str
    alias: str
    country: str
    offer_id: int
    already_exists: bool = False

    @classmethod
    def from_record(cls, record: Campaign, already_exists: bool) -> "CampaignRead":
        campaign_id, stream_id = record.keitaro_ids()
        return cls(
            campaign_id=campaign_id,
            stream_id=stream_id,
            name=record.name,
            alias=record.alias,
            country=record.country,
            offer_id=record.offer_id,
            already_exists=already_exists,
        )


class CampaignStored(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    keitaro_campaign_id: int | None
    keitaro_stream_id: int | None
    status: str
    name: str
    alias: str
    country: str
    offer_id: int
    created_at: datetime


class OfferRead(BaseModel):
    id: int
    name: str
