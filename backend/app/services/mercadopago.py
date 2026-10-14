"""Notificaciones de pago de MercadoPago → estado de suscripción del tenant.

El flujo del producto:
1. MercadoPago notifica un pago al webhook con cabecera x-signature.
2. Verificamos la firma HMAC con MP_WEBHOOK_SECRET (cabecera, sin confiar
   en el cuerpo).
3. Con el id del pago consultamos la API de MercadoPago (access token) para
   conocer su estado real — el webhook solo trae el id.
4. Pago aprobado con external_reference=tenant_id → apply_plan("premium")
   SOLO para ese tenant. Nadie más cambia.

Fase 1 (hoy): pieza completa y testeable con la API mockeada. Fase 2: crear
la preferencia de checkout desde el panel y conectar credenciales reales.
"""

import hashlib
import hmac
import logging
import time
from decimal import Decimal
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.modules_registry import PLAN_LABELS, PLAN_PRICE_COP
from app.models import Subscription, Tenant
from app.services.entitlements import apply_plan
from app.services.plan_prices import effective_price

logger = logging.getLogger(__name__)

MP_API_URL = "https://api.mercadopago.com"

# Frescura de la firma: una notificación reenviada horas después no vale
_SIGNATURE_MAX_AGE_SECONDS = 300


class PaymentSignatureError(Exception):
    """La firma de la notificación no coincide con el secreto configurado."""


def verify_signature(
    *,
    secret: str,
    x_signature: str,
    x_request_id: str | None,
    data_id: str | None,
) -> None:
    """Esquema de MercadoPago: x-signature = "ts=<ts>,v1=<hmac>".

    v1 = HMAC-SHA256 del manifest "id:{data.id};request-id:{request-id};ts:{ts};"
    — con el id alfanumérico en minúsculas si aplica — y la notificación debe
    llegar dentro de la ventana temporal (una firma vieja reenviada no vale).
    """
    parts: dict[str, str] = {}
    for chunk in x_signature.split(","):
        key, _, value = chunk.partition("=")
        parts[key.strip()] = value.strip()
    ts = parts.get("ts")
    v1 = parts.get("v1")
    if not ts or not v1:
        raise PaymentSignatureError("x-signature sin ts o v1")

    try:
        age = abs(time.time() - float(ts))
    except ValueError:
        raise PaymentSignatureError("ts no es numérico") from None
    if age > _SIGNATURE_MAX_AGE_SECONDS:
        raise PaymentSignatureError("Notificación fuera de la ventana temporal")

    raw_id = str(data_id) if data_id is not None else ""
    candidates = [raw_id]
    if raw_id and raw_id != raw_id.lower():
        # Ids alfanuméricos: MercadoPago firma el id en minúsculas
        candidates.append(raw_id.lower())

    for candidate in candidates:
        manifest = f"id:{candidate};request-id:{x_request_id or ''};ts:{ts};"
        calculated = hmac.new(
            secret.encode(), manifest.encode(), hashlib.sha256
        ).hexdigest()
        if hmac.compare_digest(calculated, v1):
            return
    raise PaymentSignatureError("Firma HMAC inválida")


async def fetch_payment(*, payment_id: str, access_token: str) -> dict:
    """GET /v1/payments/{id}: estado real del pago y su external_reference."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{MP_API_URL}/v1/payments/{payment_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()


async def create_checkout_link(
    *,
    tenant: Tenant,
    plan: str,
    access_token: str,
    notification_url: str | None = None,
    price_cop: int | None = None,
) -> dict:
    """Crea la preferencia de Checkout Pro y devuelve el link de pago.

    La preferencia lleva external_reference=tenant_id: cuando MercadoPago
    notifique el pago, el webhook sabrá a qué tenant activar el plan. El
    técnico paga en la página de MP — la tarjeta jamás pasa por aquí.
    El precio cobrado viaja en metadata.plan_price: la validación del pago
    no depende de cambios de precio hechos después de generar el link.
    """
    price = price_cop if price_cop is not None else PLAN_PRICE_COP.get(plan, 0)
    preference: dict = {
        "items": [
            {
                "id": f"{plan}_subscription",
                "title": (
                    f"Aura {PLAN_LABELS.get(plan, plan)} — {tenant.name} (1 mes)"
                ),
                "quantity": 1,
                "currency_id": "COP",
                "unit_price": price,
            }
        ],
        "external_reference": str(tenant.id),
        "metadata": {"tenant_id": str(tenant.id), "plan": plan, "plan_price": price},
    }
    if notification_url:
        preference["notification_url"] = notification_url

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{MP_API_URL}/checkout/preferences",
            headers={"Authorization": f"Bearer {access_token}"},
            json=preference,
        )
        response.raise_for_status()
        return response.json()


async def process_payment_notification(
    db: AsyncSession, *, payment_id: str, access_token: str
) -> Tenant | None:
    """Aplica el plan pagado SOLO al tenant del pago aprobado (idempotente).

    Reglas de negocio (auditoría A2):
    - Un mismo pago no se procesa dos veces (MercadoPago reenvía notificaciones).
    - El monto y la moneda deben corresponder al plan: nadie compra premium
      con $1.000 manipulando una preferencia.
    - El plan viene en el metadata de la preferencia (no está fijo).
    """
    provider_ref = f"mp:{payment_id}"

    # Idempotencia: si este pago ya dejó su fila, no hacer nada
    already = (
        await db.execute(
            select(Subscription).where(
                Subscription.provider == "mercadopago",
                Subscription.provider_ref == provider_ref,
            )
        )
    ).scalar_one_or_none()
    if already is not None:
        logger.info("Pago MP %s ya procesado: idempotente", payment_id)
        return (
            await db.execute(
                select(Tenant).where(Tenant.id == already.tenant_id)
            )
        ).scalar_one_or_none()

    payment = await fetch_payment(payment_id=payment_id, access_token=access_token)

    if payment.get("status") != "approved":
        logger.info(
            "Pago MP %s con estado %s (no es approved): no cambia ningún plan",
            payment_id,
            payment.get("status"),
        )
        return None

    reference = payment.get("external_reference")
    if not reference:
        logger.warning("Pago MP %s aprobado sin external_reference", payment_id)
        return None

    try:
        tenant_id = UUID(str(reference))
    except ValueError:
        logger.warning("Pago MP %s con external_reference inválida", payment_id)
        return None

    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if tenant is None:
        logger.warning("Pago MP %s referencia un tenant inexistente", payment_id)
        return None

    # Monto, moneda y plan: el contrato del checkout no se negocia aquí.
    # El precio esperado es el cobrado en la preferencia (metadata.plan_price);
    # preferencias previas a esa columna caen al precio vigente del plan
    # (override del panel o default del código).
    metadata = payment.get("metadata") or {}
    plan = metadata.get("plan") or "premium"
    expected_price = metadata.get("plan_price")
    if expected_price is None:
        expected_price = await effective_price(db, plan)
    try:
        amount = Decimal(str(payment.get("transaction_amount")))
    except Exception:
        amount = None
    currency = payment.get("currency_id")

    if expected_price is None or amount is None or amount != expected_price or currency != "COP":
        logger.warning(
            "Pago MP %s rechazado: monto=%s %s, plan=%s (esperado %s COP). "
            "El tenant %s NO cambia de plan.",
            payment_id,
            amount,
            currency,
            plan,
            expected_price,
            tenant.slug,
        )
        return None

    try:
        return await apply_plan(
            db,
            tenant_id=tenant.id,
            plan=plan,
            provider="mercadopago",
            provider_ref=provider_ref,
        )
    except IntegrityError:
        # Carrera: dos notificaciones del mismo pago llegaron a la vez y la
        # restricción UNIQUE(provider, provider_ref) detuvo la segunda.
        await db.rollback()
        logger.info("Pago MP %s ya existía (carrera): idempotente", payment_id)
        return tenant
