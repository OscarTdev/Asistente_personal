"""Canal Evolution API v2: parseo del webhook y envío real de mensajes.

- Entrante: texto (conversation/extendedTextMessage), imagen, audio, documento.
- Saliente: texto (sendText) y documentos base64 (sendMedia, ej. PDF).
- Configuración vía settings: EVOLUTION_API_URL / API_KEY / INSTANCE.
"""

import logging
from typing import Any

import httpx

from app.channels.base import Channel, ChannelParseError
from app.core.config import get_settings
from app.schemas.channel import IncomingMessage

logger = logging.getLogger(__name__)

# Mensajes de Baileys que mapeamos a tipos del modelo
_MEDIA_KEYS = {
    "imageMessage": "image",
    "audioMessage": "audio",
    "documentMessage": "document",
    "videoMessage": "document",  # conservador: el modelo no tiene "video"
}


class EvolutionChannel(Channel):
    name = "evolution"

    def _settings(self):
        return get_settings()

    # ── Webhook entrante ────────────────────────────────────────────────────

    async def parse_incoming(self, payload: dict[str, Any]) -> IncomingMessage:
        try:
            data = payload["data"]
            key = data["key"]
            message = data["message"]

            channel_message_id = key["id"]
            remote_jid = str(key["remoteJid"])
            wa_id = remote_jid.split("@", 1)[0]
            wa_lid: str | None = None
            if remote_jid.endswith("@lid"):
                # WhatsApp está migrando a LID (identificador interno por
                # privacidad): el teléfono real llega en el sobre del webhook
                # (sender) o en key.remoteJidAlt. Sin él se conserva el LID
                # como wa_id: el mensaje se ingesta, pero no se puede
                # responder hasta que llegue uno con el teléfono real.
                real = ""
                sender = str(payload.get("sender") or "")
                alt = str(key.get("remoteJidAlt") or "")
                if sender.endswith("@s.whatsapp.net"):
                    real = sender.split("@", 1)[0]
                elif alt.endswith("@s.whatsapp.net"):
                    real = alt.split("@", 1)[0]
                if real:
                    wa_lid = wa_id
                    wa_id = real
            push_name = data.get("pushName")
            from_me = bool(key.get("fromMe", False))
            # NOTA: los fromMe (escritos desde el teléfono del dueño) NO se
            # descartan aquí — la ingesta decide. El auto-chat ("mensaje a
            # ti mismo") es cómo el dueño le habla a su asistente cuando el
            # bot corre en su propio número.

            # Texto: conversation (sin formato) o extendedTextMessage
            extended = message.get("extendedTextMessage") or {}
            text = message.get("conversation") or extended.get("text")

            # Media: imagen / audio / documento / video
            message_type = "text"
            media_url: str | None = None
            media_base64: str | None = None
            for media_key, mapped_type in _MEDIA_KEYS.items():
                media_msg = message.get(media_key)
                if media_msg:
                    message_type = mapped_type
                    text = media_msg.get("caption")
                    media_url = media_msg.get("url")
                    media_base64 = media_msg.get("base64")
                    break

            if text is None and message_type == "text":
                # sticker, contact, reaction u otro tipo no soportado aún
                raise ChannelParseError("Mensaje sin texto ni media soportada")

            return IncomingMessage(
                channel_message_id=channel_message_id,
                wa_id=wa_id,
                wa_lid=wa_lid,
                push_name=push_name,
                message_type=message_type,
                text=text,
                from_me=from_me,
                media_url=media_url,
                media_base64=media_base64,
                raw=payload,
            )
        except ChannelParseError:
            raise
        except (KeyError, AttributeError, TypeError) as e:
            logger.debug("Error parseando payload de Evolution: %s", e, exc_info=True)
            raise ChannelParseError("Payload de webhook inválido") from e

    # ── Envío ───────────────────────────────────────────────────────────────

    def _client(self) -> httpx.AsyncClient:
        settings = self._settings()
        return httpx.AsyncClient(
            base_url=settings.evolution_api_url,
            headers={"apikey": settings.evolution_api_key},
            timeout=30,
        )

    async def send_text(self, to: str, text: str) -> str | None:
        """Envía texto vía POST /message/sendText/{instance}. Devuelve el id."""
        settings = self._settings()
        async with self._client() as client:
            response = await client.post(
                f"/message/sendText/{settings.evolution_instance}",
                json={"number": to, "text": text},
            )
            response.raise_for_status()
            data = response.json()
            message_id = (
                (data.get("key") or {}).get("id")
                or (data.get("message") or {}).get("id")
            )
            logger.debug(
                "[EvolutionChannel] Texto enviado a %s (instancia %s, id %s)",
                to,
                settings.evolution_instance,
                message_id,
            )
            return message_id

    async def send_document(
        self, to: str, file_name: str, content_base64: str, mimetype: str
    ) -> str | None:
        """Envía un documento base64 vía POST /message/sendMedia/{instance}."""
        settings = self._settings()
        async with self._client() as client:
            response = await client.post(
                f"/message/sendMedia/{settings.evolution_instance}",
                json={
                    "number": to,
                    "mediatype": "document",
                    "mimetype": mimetype,
                    "media": content_base64,
                    "fileName": file_name,
                },
            )
            response.raise_for_status()
            data = response.json()
            message_id = (
                (data.get("key") or {}).get("id")
                or (data.get("message") or {}).get("id")
            )
            logger.debug(
                "[EvolutionChannel] Documento %s enviado a %s (id %s)",
                file_name,
                to,
                message_id,
            )
            return message_id

    # ── Estado de conexión (usado por el router /whatsapp del panel) ────────

    async def connection_state(self) -> dict[str, Any]:
        """Estado de la instancia: open | close | connecting | offline."""
        settings = self._settings()
        try:
            async with self._client() as client:
                response = await client.get(
                    f"/instance/connectionState/{settings.evolution_instance}"
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            logger.warning("Evolution API no disponible: %s", exc)
            return {"instance": {"state": "offline"}}

    async def connect_qr(self) -> dict[str, Any]:
        """Inicia la conexión: crea la instancia si falta y devuelve el QR."""
        settings = self._settings()
        async with self._client() as client:
            response = await client.get(
                f"/instance/connect/{settings.evolution_instance}"
            )
            if response.status_code == 404:
                # La instancia no existe: crearla (Baileys + QR) y reconectar
                create = await client.post(
                    "/instance/create",
                    json={
                        "instanceName": settings.evolution_instance,
                        "qrcode": True,
                        "integration": "WHATSAPP-BAILEYS",
                    },
                )
                create.raise_for_status()
                response = await client.get(
                    f"/instance/connect/{settings.evolution_instance}"
                )
            response.raise_for_status()
            return response.json()

    async def disconnect(self) -> dict[str, Any]:
        """Cierra la sesión de WhatsApp (logout de la instancia).

        El número queda desvinculado: para volver a conectar hay que escanear
        el QR de nuevo (POST /whatsapp/connect).
        """
        settings = self._settings()
        async with self._client() as client:
            response = await client.delete(
                f"/instance/logout/{settings.evolution_instance}"
            )
            response.raise_for_status()
            return response.json()
