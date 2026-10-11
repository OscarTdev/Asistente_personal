"""Canal Evolution API: parseo del payload entrante y stub de envío."""

import logging
from typing import Any

from app.channels.base import Channel, ChannelParseError
from app.schemas.channel import IncomingMessage

logger = logging.getLogger(__name__)


class EvolutionChannel(Channel):
    name = "evolution"

    async def parse_incoming(self, payload: dict[str, Any]) -> IncomingMessage:
        try:
            data = payload["data"]
            key = data["key"]
            message = data["message"]

            channel_message_id = key["id"]
            wa_id = key["remoteJid"].split("@", 1)[0]
            push_name = data.get("pushName")

            # F1: solo mensajes de texto. La extracción es por contenido, no por
            # messageType ("conversation" y "extendedTextMessage" son variantes
            # de texto en Evolution). Sin texto extraíble → error de parseo.
            extended = message.get("extendedTextMessage") or {}
            text = message.get("conversation") or extended.get("text")
            if text is None:
                raise ChannelParseError("No se pudo extraer texto del mensaje")

            return IncomingMessage(
                channel_message_id=channel_message_id,
                wa_id=wa_id,
                push_name=push_name,
                message_type="text",
                text=text,
                raw=payload,
            )
        except ChannelParseError:
            raise
        except (KeyError, AttributeError, TypeError) as e:
            logger.debug("Error parseando payload de Evolution: %s", e, exc_info=True)
            raise ChannelParseError("Payload de webhook inválido") from e

    async def send_text(self, to: str, text: str) -> None:
        """Stub: solo registra el intento de envío (F1)."""
        logger.info("[EvolutionChannel] Enviando mensaje a %s: %s", to, text)
