"""Publicación de eventos en Redis pub/sub."""

import logging
from uuid import UUID

from redis.asyncio import Redis

from app.models import Event
from app.schemas.events import EventOut

logger = logging.getLogger(__name__)


def events_channel(tenant_id: UUID | str) -> str:
    """Canal de Redis de eventos para un tenant."""
    return f"events:{tenant_id}"


async def publish_event(client: Redis, tenant_id: UUID, event: Event) -> None:
    """Publica el evento en el canal Redis del tenant.

    Propaga excepciones: el llamador decide si un fallo de Redis rompe el
    request (el webhook no debe romperse; otros consumidores sí).
    """
    # UUIDs como str: psycopg no serializa UUID dentro de JSONB y el cliente
    # del feed consume JSON plano.
    event_out = EventOut(
        id=event.id,
        tenant_id=event.tenant_id,
        type=event.type,
        created_at=event.created_at,
        data=event.payload or {},
    )
    body = event_out.model_dump_json()
    await client.publish(events_channel(tenant_id), body)
    logger.debug("Evento %s publicado en %s", event.id, events_channel(tenant_id))
