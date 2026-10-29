"""Esquemas del panel de administración de la plataforma."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlanChangeRequest(BaseModel):
    plan: str = Field(pattern="^(trial|freemium|premium)$")


class TenantWhatsappUpdate(BaseModel):
    """Número de WhatsApp del dueño del tenant (la llave de enrutamiento)."""

    wa_id: str | None = Field(default=None, pattern=r"^[0-9]{5,20}$")


class TenantUpdateRequest(BaseModel):
    """Edición de un cliente registrado: nombre del negocio/persona y del bot."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    bot_name: str | None = Field(default=None, min_length=1, max_length=50)
    customer_mode: bool | None = None


class ChannelIdentityCreate(BaseModel):
    """Vincula una identidad de canal a un contacto (su Telegram, su app)."""

    channel: Literal["whatsapp", "telegram", "web"]
    external_id: str = Field(min_length=1, max_length=100)
    kind: Literal["owner", "team", "contact"] = "contact"


class ChannelIdentityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel: str
    external_id: str
    kind: str
    contact_id: UUID
    created_at: datetime


class CheckoutLinkRequest(BaseModel):
    send_to_whatsapp: bool = False


class CheckoutLinkResult(BaseModel):
    preference_id: str | None
    init_point: str
    plan: str
    price_cop: int
    whatsapp_sent: bool


class PlanPriceOut(BaseModel):
    plan: str
    label: str
    price_cop: int
    is_overridden: bool


class PlanPriceUpdate(BaseModel):
    price_cop: int = Field(ge=0, le=10_000_000)


class ModuleToggleRequest(BaseModel):
    is_enabled: bool


class PaymentMethodCreate(BaseModel):
    """Modo manual: el admin registra la tarjeta resumida (brand + últimos 4).

    Con la pasarela real (MercadoPago) este cuerpo llega tokenizado desde el
    webhook — el servidor nunca ve el número completo.
    """

    brand: str = Field(min_length=1, max_length=30)
    last4: str = Field(pattern="^[0-9]{4}$")
    exp_month: int | None = Field(default=None, ge=1, le=12)
    exp_year: int | None = Field(default=None, ge=2024, le=2100)


class PaymentMethodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: str
    brand: str
    last4: str
    exp_month: int | None
    exp_year: int | None
    is_default: bool
    created_at: datetime


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_key: str
    status: str
    provider: str
    current_period_start: datetime | None
    current_period_end: datetime | None
    created_at: datetime


class ModuleAdminView(BaseModel):
    key: str
    name: str
    category: str
    dev_status: str
    is_enabled: bool
    entitled: bool


class TenantAdminSummary(BaseModel):
    id: UUID
    name: str
    slug: str
    bot_name: str
    is_active: bool
    plan: str
    plan_label: str
    plan_price_cop: int
    wa_id: str | None
    account_type: str
    nit: str | None
    customer_mode: bool
    subscription_status: str | None
    subscription_period_end: datetime | None
    enabled_modules: int
    total_modules: int
    contacts: int
    quotes: int
    messages: int
    users: int


class TenantAdminDetail(TenantAdminSummary):
    modules: list[ModuleAdminView]
    payment_methods: list[PaymentMethodOut]
    subscription: SubscriptionOut | None
    last_message_at: datetime | None = None
    last_quote_at: datetime | None = None
    total_quotes_amount: float = 0
    quotes_last_30d: int = 0
    active_services: list[str] = []


class TenantStatusUpdate(BaseModel):
    is_active: bool


class PlatformServiceStat(BaseModel):
    key: str
    name: str
    interactions: int
    tenants: int


class PlatformPlanStat(BaseModel):
    plan: str
    count: int


class PlatformAdminStats(BaseModel):
    total_tenants: int
    active_tenants: int
    blocked_tenants: int
    total_messages: int
    total_quotes: int
    services: list[PlatformServiceStat]
    plans: list[PlatformPlanStat]


class ConversationAdminItem(BaseModel):
    id: UUID
    contact_id: UUID
    contact_name: str | None
    contact_wa_id: str
    status: str
    messages_count: int
    last_message_at: datetime | None


class ConversationAdminPage(BaseModel):
    items: list[ConversationAdminItem]
    total: int


class MessageAdminItem(BaseModel):
    id: UUID
    direction: str
    type: str
    content: str | None
    created_at: datetime


class MessageAdminPage(BaseModel):
    items: list[MessageAdminItem]
    total: int


class AdminMessageRequest(BaseModel):
    message: str


class AdminMessageResponse(BaseModel):
    message_id: str
