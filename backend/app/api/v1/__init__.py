from fastapi import APIRouter

from .auth import router as auth_router
from .catalog import router as catalog_router
from .contacts import router as contacts_router
from .dashboard import router as dashboard_router
from .modules import router as modules_router
from .quotes import router as quotes_router
from .webhooks import router as webhooks_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(modules_router, prefix="/modules", tags=["modules"])
api_router.include_router(contacts_router, prefix="/contacts", tags=["contacts"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(catalog_router, prefix="/catalog", tags=["catalog"])
api_router.include_router(quotes_router, prefix="/quotes", tags=["quotes"])
api_router.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])