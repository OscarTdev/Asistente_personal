from fastapi import APIRouter

from .auth import router as auth_router
from .webhooks import router as webhooks_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])