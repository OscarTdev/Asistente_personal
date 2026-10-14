"""Administración de la plataforma (solo is_platform_admin).

Gestiona los tenants (los clientes de la plataforma): plan de suscripción,
métodos de pago tokenizados, servicios con contrato de entitlements y el
historial de chat de cada tenant.
"""

import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_admin
from app.channels import get_channel
from app.core.config import get_settings
from app.core.database import get_db
from app.core.modules_registry import (
    AVAILABLE_MODULES,
    PLAN_LABELS,
    PLAN_PRICE_COP,
    module_dev_status,
    plan_allows,
)
from app.models import (
    ChannelIdentity,
    Contact,
    Conversation,
    Message,
    PaymentMethod,
    Quote,
    Subscription,
    Tenant,
    TenantModule,
    User,
)
from app.schemas.admin import (
    ChannelIdentityCreate,
    ChannelIdentityOut,
    CheckoutLinkRequest,
    CheckoutLinkResult,
    ConversationAdminItem,
    ConversationAdminPage,
    MessageAdminItem,
    MessageAdminPage,
    ModuleAdminView,
    ModuleToggleRequest,
    PaymentMethodCreate,
    PlanChangeRequest,
    TenantAdminDetail,
    TenantAdminSummary,
    TenantUpdateRequest,
    TenantWhatsappUpdate,
)
from app.services.entitlements import apply_plan
from app.services.identity import link_identity
from app.services.mercadopago import create_checkout_link

logger = logging.getLogger(__name__)
router = APIRouter()


async def _get_tenant_or_404(db: AsyncSession, tenant_id: UUID) -> Tenant:
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant no encontrado"
        )
    return tenant


async def _latest_subscription(
    db: AsyncSession, tenant_id: UUID
) -> Subscription | None:
    return (
        await db.execute(
            select(Subscription)
            .where(Subscription.tenant_id == tenant_id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _count_by_tenant(db: AsyncSession, model) -> dict[UUID, int]:
    rows = (
        await db.execute(
            select(model.tenant_id, func.count()).group_by(model.tenant_id)
        )
    ).all()
    return {tenant_id: count for tenant_id, count in rows}


def _summary(
    tenant: Tenant,
    *,
    sub: Subscription | None,
    enabled_modules: int,
    counts: dict[str, int],
) -> TenantAdminSummary:
    return TenantAdminSummary(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        bot_name=tenant.bot_name,
        is_active=tenant.is_active,
        plan=tenant.plan,
        plan_label=PLAN_LABELS.get(tenant.plan, tenant.plan),
        plan_price_cop=PLAN_PRICE_COP.get(tenant.plan, 0),
        wa_id=tenant.wa_id,
        account_type=tenant.account_type,
        nit=tenant.nit,
        customer_mode=tenant.customer_mode,
        subscription_status=sub.status if sub else None,
        subscription_period_end=sub.current_period_end if sub else None,
        enabled_modules=enabled_modules,
        total_modules=len(AVAILABLE_MODULES),
        contacts=counts.get("contacts", 0),
        quotes=counts.get("quotes", 0),
        messages=counts.get("messages", 0),
        users=counts.get("users", 0),
    )


async def _tenant_detail(db: AsyncSession, tenant: Tenant) -> TenantAdminDetail:
    sub = await _latest_subscription(db, tenant.id)

    modules = (
        await db.execute(
            select(TenantModule)
            .where(TenantModule.tenant_id == tenant.id)
            .order_by(TenantModule.category, TenantModule.name)
        )
    ).scalars().all()

    payment_methods = (
        await db.execute(
            select(PaymentMethod)
            .where(PaymentMethod.tenant_id == tenant.id)
            .order_by(PaymentMethod.is_default.desc(), PaymentMethod.created_at.desc())
        )
    ).scalars().all()

    counts = {
        "contacts": (await _count_by_tenant(db, Contact)).get(tenant.id, 0),
        "quotes": (await _count_by_tenant(db, Quote)).get(tenant.id, 0),
        "messages": (await _count_by_tenant(db, Message)).get(tenant.id, 0),
        "users": (await _count_by_tenant(db, User)).get(tenant.id, 0),
    }
    enabled_modules = (
        await db.execute(
            select(func.count())
            .select_from(TenantModule)
            .where(TenantModule.tenant_id == tenant.id, TenantModule.is_enabled)
        )
    ).scalar_one()

    return TenantAdminDetail(
        **_summary(
            tenant, sub=sub, enabled_modules=enabled_modules, counts=counts
        ).model_dump(),
        modules=[
            ModuleAdminView(
                key=tm.module_key,
                name=tm.name,
                category=tm.category,
                dev_status=module_dev_status(tm.module_key),
                is_enabled=tm.is_enabled,
                entitled=plan_allows(tenant.plan, tm.module_key),
            )
            for tm in modules
        ],
        payment_methods=list(payment_methods),
        subscription=sub,
    )


# ── Tenants ─────────────────────────────────────────────────────────────────


@router.get("/tenants", response_model=list[TenantAdminSummary])
async def list_tenants(
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> list[TenantAdminSummary]:
    """Lista los clientes de la plataforma con su plan y uso."""
    tenants = (
        await db.execute(select(Tenant).order_by(Tenant.name))
    ).scalars().all()

    contacts = await _count_by_tenant(db, Contact)
    quotes = await _count_by_tenant(db, Quote)
    messages = await _count_by_tenant(db, Message)
    users = await _count_by_tenant(db, User)
    enabled_rows = (
        await db.execute(
            select(TenantModule.tenant_id, func.count())
            .where(TenantModule.is_enabled)
            .group_by(TenantModule.tenant_id)
        )
    ).all()
    enabled = {tid: count for tid, count in enabled_rows}

    # Última suscripción por tenant (iterando de la más reciente a la más vieja)
    subs: dict[UUID, Subscription] = {}
    all_subs = (
        await db.execute(
            select(Subscription).order_by(Subscription.created_at.desc())
        )
    ).scalars().all()
    for sub in all_subs:
        subs.setdefault(sub.tenant_id, sub)

    result = []
    for tenant in tenants:
        sub = subs.get(tenant.id)
        result.append(
            _summary(
                tenant,
                sub=sub,
                enabled_modules=enabled.get(tenant.id, 0),
                counts={
                    "contacts": contacts.get(tenant.id, 0),
                    "quotes": quotes.get(tenant.id, 0),
                    "messages": messages.get(tenant.id, 0),
                    "users": users.get(tenant.id, 0),
                },
            )
        )
    return result


@router.get("/tenants/{tenant_id}", response_model=TenantAdminDetail)
async def get_tenant(
    tenant_id: UUID,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantAdminDetail:
    """Detalle de un cliente: servicios, métodos de pago y suscripción."""
    tenant = await _get_tenant_or_404(db, tenant_id)
    return await _tenant_detail(db, tenant)


@router.patch("/tenants/{tenant_id}/plan", response_model=TenantAdminDetail)
async def change_plan(
    tenant_id: UUID,
    body: PlanChangeRequest,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantAdminDetail:
    """Cambia el plan de un cliente y sincroniza sus servicios."""
    tenant = await _get_tenant_or_404(db, tenant_id)
    tenant = await apply_plan(db, tenant_id=tenant.id, plan=body.plan)
    return await _tenant_detail(db, tenant)


@router.patch("/tenants/{tenant_id}", response_model=TenantAdminDetail)
async def update_tenant(
    tenant_id: UUID,
    body: TenantUpdateRequest,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantAdminDetail:
    """Edita los datos de un cliente: nombre del negocio/persona y del bot.

    El nombre editado es el que llevan las cotizaciones que se generen a
    partir de ese momento (encabezado y pie del PDF).
    """
    tenant = await _get_tenant_or_404(db, tenant_id)

    if body.name is not None:
        tenant.name = body.name.strip()
    if body.bot_name is not None:
        bot_name = body.bot_name.strip()
        if bot_name:
            tenant.bot_name = bot_name
    if body.customer_mode is not None:
        # Atención al cliente por chat: apagada por defecto (Enmienda A)
        tenant.customer_mode = body.customer_mode

    await db.commit()
    await db.refresh(tenant)
    return await _tenant_detail(db, tenant)


@router.put("/tenants/{tenant_id}/whatsapp", response_model=TenantAdminDetail)
async def set_tenant_whatsapp(
    tenant_id: UUID,
    body: TenantWhatsappUpdate,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantAdminDetail:
    """Registra el número de WhatsApp del dueño (llave de enrutamiento).

    Con un número de bot compartido, el webhook identifica quién escribe por
    este campo. Un número solo puede pertenecer a un tenant. None lo libera.
    """
    tenant = await _get_tenant_or_404(db, tenant_id)

    if body.wa_id:
        clash = (
            await db.execute(
                select(Tenant).where(
                    Tenant.wa_id == body.wa_id, Tenant.id != tenant.id
                )
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ese número ya pertenece al cliente '{clash.name}'",
            )

    tenant.wa_id = body.wa_id or None
    await db.commit()
    await db.refresh(tenant)
    return await _tenant_detail(db, tenant)


# ── Métodos de pago (proveedor manual; MercadoPago en la fase 2) ───────────


@router.post(
    "/tenants/{tenant_id}/payment-method", response_model=TenantAdminDetail
)
async def add_payment_method(
    tenant_id: UUID,
    body: PaymentMethodCreate,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantAdminDetail:
    """Registra un método de pago tokenizado.

    Regla de negocio: si el cliente está en trial, registrar el método lo
    pasa a freemium (sus servicios autorizados se activan solos).
    """
    tenant = await _get_tenant_or_404(db, tenant_id)

    existing_count = (
        await db.execute(
            select(func.count())
            .select_from(PaymentMethod)
            .where(PaymentMethod.tenant_id == tenant.id)
        )
    ).scalar_one()

    db.add(
        PaymentMethod(
            tenant_id=tenant.id,
            provider="manual",
            provider_token=f"manual-{uuid4()}",
            brand=body.brand.strip(),
            last4=body.last4,
            exp_month=body.exp_month,
            exp_year=body.exp_year,
            is_default=existing_count == 0,
        )
    )
    await db.commit()

    if tenant.plan == "trial":
        tenant = await apply_plan(db, tenant_id=tenant.id, plan="freemium")
    return await _tenant_detail(db, tenant)


@router.delete(
    "/tenants/{tenant_id}/payment-methods/{payment_method_id}",
    response_model=TenantAdminDetail,
)
async def delete_payment_method(
    tenant_id: UUID,
    payment_method_id: UUID,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantAdminDetail:
    """Elimina un método de pago.

    Regla de negocio: si era el último y el cliente está en freemium, vuelve
    a trial (freemium exige método de pago en archivo).
    """
    tenant = await _get_tenant_or_404(db, tenant_id)

    payment_method = (
        await db.execute(
            select(PaymentMethod).where(
                PaymentMethod.id == payment_method_id,
                PaymentMethod.tenant_id == tenant.id,
            )
        )
    ).scalar_one_or_none()
    if payment_method is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Método de pago no encontrado",
        )

    await db.delete(payment_method)
    await db.commit()

    remaining = (
        await db.execute(
            select(func.count())
            .select_from(PaymentMethod)
            .where(PaymentMethod.tenant_id == tenant.id)
        )
    ).scalar_one()

    if remaining == 0 and tenant.plan == "freemium":
        tenant = await apply_plan(db, tenant_id=tenant.id, plan="trial")
    return await _tenant_detail(db, tenant)


# ── Servicios por tenant (contrato de entitlements) ────────────────────────


@router.put(
    "/tenants/{tenant_id}/modules/{module_key}", response_model=ModuleAdminView
)
async def toggle_tenant_module(
    tenant_id: UUID,
    module_key: str,
    body: ModuleToggleRequest,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> ModuleAdminView:
    """Enciende/apaga un servicio de un cliente — nunca fuera de su plan."""
    tenant = await _get_tenant_or_404(db, tenant_id)

    module = (
        await db.execute(
            select(TenantModule).where(
                TenantModule.tenant_id == tenant.id,
                TenantModule.module_key == module_key,
            )
        )
    ).scalar_one_or_none()
    if module is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Servicio '{module_key}' no encontrado",
        )

    if body.is_enabled and not plan_allows(tenant.plan, module_key):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"El plan {PLAN_LABELS.get(tenant.plan, tenant.plan)} no incluye "
                f"el servicio '{module.name}'. Actualiza el plan para activarlo."
            ),
        )

    module.is_enabled = body.is_enabled
    await db.commit()
    await db.refresh(module)

    return ModuleAdminView(
        key=module.module_key,
        name=module.name,
        category=module.category,
        dev_status=module_dev_status(module.module_key),
        is_enabled=module.is_enabled,
        entitled=plan_allows(tenant.plan, module.module_key),
    )


# ── Identidades por canal (multi-canal: WhatsApp, Telegram, app) ───────────


@router.get(
    "/tenants/{tenant_id}/contacts/{contact_id}/identities",
    response_model=list[ChannelIdentityOut],
)
async def list_contact_identities(
    tenant_id: UUID,
    contact_id: UUID,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> list[ChannelIdentityOut]:
    """Las puertas de un contacto: por dónde puede hablarle al asistente."""
    tenant = await _get_tenant_or_404(db, tenant_id)

    contact = (
        await db.execute(
            select(Contact).where(
                Contact.id == contact_id, Contact.tenant_id == tenant.id
            )
        )
    ).scalar_one_or_none()
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Contacto no encontrado"
        )

    rows = (
        await db.execute(
            select(ChannelIdentity)
            .where(
                ChannelIdentity.tenant_id == tenant.id,
                ChannelIdentity.contact_id == contact.id,
            )
            .order_by(ChannelIdentity.created_at.desc())
        )
    ).scalars().all()
    return list(rows)


@router.post(
    "/tenants/{tenant_id}/contacts/{contact_id}/identities",
    response_model=ChannelIdentityOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_contact_identity(
    tenant_id: UUID,
    contact_id: UUID,
    body: ChannelIdentityCreate,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> ChannelIdentityOut:
    """Vincula una identidad nueva a un contacto (p. ej. su usuario de Telegram).

    A partir de ese momento, escribir por ese canal es el mismo usuario con
    el mismo historial — no pierde nada al cambiar de puerta.
    """
    tenant = await _get_tenant_or_404(db, tenant_id)

    contact = (
        await db.execute(
            select(Contact).where(
                Contact.id == contact_id, Contact.tenant_id == tenant.id
            )
        )
    ).scalar_one_or_none()
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Contacto no encontrado"
        )

    clash = (
        await db.execute(
            select(ChannelIdentity).where(
                ChannelIdentity.channel == body.channel,
                ChannelIdentity.external_id == body.external_id,
            )
        )
    ).scalar_one_or_none()
    if clash is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese identificador ya pertenece a otro contacto",
        )

    try:
        identity = await link_identity(
            db,
            tenant=tenant,
            contact=contact,
            kind=body.kind,
            channel=body.channel,
            external_id=body.external_id,
        )
        await db.commit()
        await db.refresh(identity)
        return identity
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese identificador ya pertenece a otro contacto",
        ) from None


@router.delete(
    "/tenants/{tenant_id}/identities/{identity_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_contact_identity(
    tenant_id: UUID,
    identity_id: UUID,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Desvincula una puerta: el contacto sigue intacto en su núcleo."""
    await _get_tenant_or_404(db, tenant_id)

    identity = (
        await db.execute(
            select(ChannelIdentity).where(
                ChannelIdentity.id == identity_id,
                ChannelIdentity.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Identidad no encontrada",
        )

    await db.delete(identity)
    await db.commit()


# ── Link de pago (MercadoPago Checkout Pro) ────────────────────────────────


@router.post(
    "/tenants/{tenant_id}/checkout-link", response_model=CheckoutLinkResult
)
async def create_tenant_checkout_link(
    tenant_id: UUID,
    body: CheckoutLinkRequest | None = None,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> CheckoutLinkResult:
    """Genera el link de pago de MercadoPago para subir de plan.

    El técnico paga en la página de MP (Checkout Pro); la preferencia lleva
    external_reference=tenant_id para que el webhook active el premium SOLO
    de quien pagó. Con send_to_whatsapp el link se le envía por el chat.
    """
    settings = get_settings()
    if not settings.mercadopago_access_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "MercadoPago sin configurar: falta MERCADOPAGO_ACCESS_TOKEN "
                "(mientras tanto, cambia el plan manualmente)"
            ),
        )

    tenant = await _get_tenant_or_404(db, tenant_id)

    send_to_whatsapp = bool(body and body.send_to_whatsapp)
    if send_to_whatsapp and not tenant.wa_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El cliente no tiene WhatsApp registrado: regístralo primero",
        )

    try:
        preference = await create_checkout_link(
            tenant=tenant,
            plan="premium",
            access_token=settings.mercadopago_access_token,
            notification_url=settings.mercadopago_notification_url or None,
        )
    except Exception as exc:
        logger.exception("MercadoPago rechazó crear la preferencia")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="MercadoPago no pudo crear el link de pago",
        ) from exc

    link = preference.get("init_point") or preference.get("sandbox_init_point") or ""

    whatsapp_sent = False
    if send_to_whatsapp and link:
        channel = get_channel("evolution")
        await channel.send_text(
            tenant.wa_id,
            f"¡Sube a Premium! Paga tu suscripción aquí: {link}",
        )
        whatsapp_sent = True

    return CheckoutLinkResult(
        preference_id=preference.get("id"),
        init_point=link,
        plan="premium",
        price_cop=PLAN_PRICE_COP["premium"],
        whatsapp_sent=whatsapp_sent,
    )


# ── Historial de chat ──────────────────────────────────────────────────────


@router.get(
    "/tenants/{tenant_id}/conversations", response_model=ConversationAdminPage
)
async def list_tenant_conversations(
    tenant_id: UUID,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> ConversationAdminPage:
    """Conversaciones de un cliente (sus chats de WhatsApp)."""
    tenant = await _get_tenant_or_404(db, tenant_id)

    total = (
        await db.execute(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.tenant_id == tenant.id)
        )
    ).scalar_one()

    conversations = (
        await db.execute(
            select(Conversation)
            .where(Conversation.tenant_id == tenant.id)
            .order_by(
                Conversation.last_message_at.desc().nullslast(),
                Conversation.id.desc(),
            )
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()

    contact_ids = [c.contact_id for c in conversations]
    contacts_by_id: dict[UUID, Contact] = {}
    messages_count: dict[UUID, int] = {}
    if contact_ids:
        contacts_by_id = {
            contact.id: contact
            for contact in (
                await db.execute(
                    select(Contact).where(Contact.id.in_(contact_ids))
                )
            ).scalars()
        }
        rows = (
            await db.execute(
                select(Message.conversation_id, func.count())
                .where(
                    Message.conversation_id.in_([c.id for c in conversations])
                )
                .group_by(Message.conversation_id)
            )
        ).all()
        messages_count = {cid: count for cid, count in rows}

    items = [
        ConversationAdminItem(
            id=c.id,
            contact_id=c.contact_id,
            contact_name=contacts_by_id[c.contact_id].name
            if c.contact_id in contacts_by_id
            else None,
            contact_wa_id=contacts_by_id[c.contact_id].wa_id
            if c.contact_id in contacts_by_id
            else "",
            status=c.status,
            messages_count=messages_count.get(c.id, 0),
            last_message_at=c.last_message_at,
        )
        for c in conversations
    ]
    return ConversationAdminPage(items=items, total=total)


@router.get(
    "/tenants/{tenant_id}/conversations/{conversation_id}/messages",
    response_model=MessageAdminPage,
)
async def list_conversation_messages(
    tenant_id: UUID,
    conversation_id: UUID,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
) -> MessageAdminPage:
    """Mensajes de una conversación (aislamiento por tenant verificado)."""
    tenant = await _get_tenant_or_404(db, tenant_id)

    conversation = (
        await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant.id,
            )
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada",
        )

    total = (
        await db.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation.id)
        )
    ).scalar_one()

    rows = (
        await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    # Últimos N en orden cronológico (los chats se leen de abajo hacia arriba)
    messages = list(reversed(rows))

    return MessageAdminPage(
        items=[
            MessageAdminItem(
                id=m.id,
                direction=m.direction,
                type=m.type,
                content=m.content,
                created_at=m.created_at,
            )
            for m in messages
        ],
        total=total,
    )
