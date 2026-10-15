from fastapi import APIRouter

from .admin import router as admin_router
from .auth import router as auth_router
from .branding import router as branding_router
from .catalog import router as catalog_router
from .contacts import router as contacts_router
from .dashboard import router as dashboard_router
from .followup import router as followup_router
from .modules import router as modules_router
from .quotes import router as quotes_router
from .reminders import router as reminders_router
from .webhooks import router as webhooks_router
from .whatsapp import router as whatsapp_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(branding_router, prefix="/branding", tags=["branding"])
api_router.include_router(modules_router, prefix="/modules", tags=["modules"])
api_router.include_router(contacts_router, prefix="/contacts", tags=["contacts"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(catalog_router, prefix="/catalog", tags=["catalog"])
api_router.include_router(quotes_router, prefix="/quotes", tags=["quotes"])
api_router.include_router(followup_router, prefix="/followup", tags=["followup"])
api_router.include_router(reminders_router, prefix="/reminders", tags=["reminders"])
api_router.include_router(whatsapp_router, prefix="/whatsapp", tags=["whatsapp"])
api_router.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])