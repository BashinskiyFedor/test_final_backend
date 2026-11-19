from fastapi import APIRouter

from app.api.routes import campaigns, streams

api_router = APIRouter()
api_router.include_router(campaigns.router)
api_router.include_router(campaigns.offers_router)
api_router.include_router(streams.router)
