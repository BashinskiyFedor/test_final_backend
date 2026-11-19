from pydantic import BaseModel, ConfigDict


class StreamOfferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    offer_id: int
    name: str
    share: int
    pinned: bool
    active: bool
    in_keitaro: bool
    is_new: bool


class StreamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    keitaro_stream_id: int
    name: str
    type: str
    has_offers: bool
    dirty: bool
    offers: list[StreamOfferRead]


class OfferAdd(BaseModel):
    offer_id: int


class OfferPin(BaseModel):
    pinned: bool
