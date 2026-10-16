"""Registro central de módulos disponibles en el asistente.

Los módulos aquí listados son los que el admin puede activar/desactivar
por tenant. La tabla tenant_modules solo almacena el estado (enabled/disabled).
Para agregar un módulo futuro, basta con añadir una entrada aquí.

`dev_status` dice si el servicio YA está construido ("active") o si es un
servicio planeado que se perfeccionará uno a uno ("development").
"""

from typing import TypedDict


class ModuleDefinition(TypedDict):
    key: str
    name: str
    description: str
    category: str
    dev_status: str  # "active" | "development"


AVAILABLE_MODULES: list[ModuleDefinition] = [
    # ── Oficios ──────────────────────────────────────────────────────────
    {
        "key": "quoter",
        "name": "Cotizador",
        "description": (
            "El técnico envía audio, foto o texto y el bot genera una cotización "
            "en PDF desde el catálogo de precios propio."
        ),
        "category": "oficios",
    },
    {
        "key": "follow_up",
        "name": "Seguimiento de cotizaciones",
        "description": (
            "Escribe al cliente a los 3 y 7 días de enviar una cotización. "
            "El módulo que más dinero recupera."
        ),
        "category": "oficios",
    },
    {
        "key": "collections",
        "name": "Cobro de cartera",
        "description": (
            "Recordatorios amables de pagos pendientes con enlace de pago incluido."
        ),
        "category": "oficios",
    },
    {
        "key": "visit_report",
        "name": "Informe de visita técnica",
        "description": (
            "Fotos y audio se convierten en un PDF con hallazgos y recomendaciones "
            "listo para compartir con el cliente."
        ),
        "category": "oficios",
    },
    {
        "key": "maintenance",
        "name": "Mantenimiento preventivo",
        "description": (
            "Avisa a los clientes cuándo toca limpiar el aire o revisar el tablero. "
            "Genera ingresos recurrentes."
        ),
        "category": "oficios",
    },
    {
        "key": "site_log",
        "name": "Seguimiento de obra",
        "description": (
            "Bitácora diaria, avance con fotos y reporte automático al cliente."
        ),
        "category": "oficios",
    },
    {
        "key": "inventory",
        "name": "Materiales e inventario",
        "description": (
            "Lista de materiales de cada cotización, pedido al proveedor "
            "y control de lo que sobra."
        ),
        "category": "oficios",
    },
    {
        "key": "profitability",
        "name": "Rentabilidad por obra",
        "description": (
            "Costo real contra lo cotizado para saber qué trabajos dejan plata."
        ),
        "category": "oficios",
    },
    {
        "key": "warranties",
        "name": "Garantías",
        "description": (
            "Registra qué se instaló, cuándo y hasta cuándo cubre la garantía."
        ),
        "category": "oficios",
    },
    # ── Base (transversales) ─────────────────────────────────────────────
    {
        "key": "reminders",
        "name": "Recordatorios y agenda",
        "description": (
            '"Recuérdame llamar al cliente de Laureles el jueves." '
            "Es el módulo que más hace volver al usuario."
        ),
        "category": "base",
    },
    {
        "key": "crm",
        "name": "Contactos y clientes (mini CRM)",
        "description": (
            "Historial de cada cliente, cotizaciones, trabajos y notas. "
            "El bot recuerda quién es quién."
        ),
        "category": "base",
    },
    {
        "key": "voice_notes",
        "name": "Notas por voz y tareas",
        "description": (
            "El técnico dicta y el bot lo ordena en tareas con fecha."
        ),
        "category": "base",
    },
    {
        "key": "daily_summary",
        "name": "Resumen diario proactivo",
        "description": (
            "Cada mañana: qué hay agendado, qué cotizaciones esperan respuesta "
            "y qué pagos están pendientes."
        ),
        "category": "base",
    },
    # ── General ──────────────────────────────────────────────────────────
    {
        "key": "email_calendar",
        "name": "Correo y calendario",
        "description": (
            "Resumir el correo, proponer horarios y crear eventos en Google Calendar. "
            "Siempre con confirmación antes de enviar."
        ),
        "category": "general",
    },
    {
        "key": "personal_finance",
        "name": "Finanzas personales",
        "description": (
            "Gastos por voz o foto de recibo y resumen mensual automático."
        ),
        "category": "general",
    },
]

# Servicios ya construidos; el resto se listan como "En desarrollo"
DEV_STATUS: dict[str, str] = {
    "quoter": "active",
    "follow_up": "active",
    "crm": "active",
    "reminders": "active",
    "voice_notes": "active",  # STT (F7) + notas + recordatorios ya funcionan
    "collections": "active",  # cobro de cartera con link de MercadoPago
    "visit_report": "active",  # informe de visita técnica IV-0001
    "maintenance": "active",   # mantenimiento preventivo recurrente
    "warranties": "active",    # garantías de lo instalado
    "personal_finance": "active",  # gastos por voz + resumen mensual
    "inventory": "active",      # materiales e inventario del técnico
}

# Workspace del panel para servicios activos (donde vive "Entrar")
WORKSPACE_ROUTE: dict[str, str] = {
    "quoter": "/servicios/quoter",
    "crm": "/servicios/crm",
    "reminders": "/servicios/reminders",
}

# Sub-servicios: viven DENTRO del workspace de su servicio padre, no como
# carta propia en la lista de Servicios (p. ej. el seguimiento del cotizador)
PARENT_MODULE: dict[str, str] = {"follow_up": "quoter"}


def module_dev_status(key: str) -> str:
    """Estado de desarrollo del servicio: construido o planeado."""
    return DEV_STATUS.get(key, "development")


def module_workspace(key: str) -> str | None:
    """Ruta del espacio de trabajo del panel si el servicio está construido."""
    if module_dev_status(key) != "active":
        return None
    return WORKSPACE_ROUTE.get(key)


def module_parent(key: str) -> str | None:
    """Servicio padre si este módulo es un sub-servicio (None = carta propia)."""
    return PARENT_MODULE.get(key)


# ── Planes de suscripción ─────────────────────────────────────────────────
# Qué servicios autoriza cada nivel. Cambiar esto no requiere migración:
# el plan se aplica con services/entitlements.apply_plan().
#   trial    → sin método de pago: probar el cotizador
#   freemium → método de pago registrado, sin suscripción activa
#   premium  → suscripción activa: todos los servicios
PLAN_ENTITLEMENTS: dict[str, list[str]] = {
    "trial": ["quoter"],
    "freemium": ["quoter", "reminders"],
    "premium": [m["key"] for m in AVAILABLE_MODULES],
}

PLAN_LABELS: dict[str, str] = {
    "trial": "Prueba",
    "freemium": "Freemium",
    "premium": "Premium",
}

PLAN_PRICE_COP: dict[str, int] = {
    "trial": 0,
    "freemium": 0,
    "premium": 19_900,
}


def plan_entitlements(plan: str) -> list[str]:
    """Servicios incluidos en un plan (desconocido → los del trial)."""
    return PLAN_ENTITLEMENTS.get(plan, PLAN_ENTITLEMENTS["trial"])


def plan_allows(plan: str, module_key: str) -> bool:
    """¿El plan autoriza este servicio?"""
    return module_key in plan_entitlements(plan)


# Índice rápido por key
MODULES_BY_KEY: dict[str, ModuleDefinition] = {m["key"]: m for m in AVAILABLE_MODULES}
