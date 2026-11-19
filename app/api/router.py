from fastapi import APIRouter

from app.api.routes import campaigns, items

api_router = APIRouter()
api_router.include_router(items.router)
api_router.include_router(campaigns.router)
api_router.include_router(campaigns.offers_router)
