"""Canal Evolution API v2: parseo del webhook y envío real de mensajes.

- Entrante: texto (conversation/extendedTextMessage), imagen, audio, documento.
- Saliente: texto (sendText), documentos base64 (sendMedia, ej. PDF) y
  notas de voz (sendWhatsAppAudio).
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
                # WhatsApp usa LID (identificador interno) cuando la persona
                # oculta su número (usuario con @nombre). Si el teléfono real
                # llega en key.remoteJidAlt, el contacto se identifica por
                # teléfono y el LID queda como alias. OJO: el «sender» del
                # sobre del webhook de Evolution es el JID de la PROPIA
                # instancia (el número del bot), NO quien escribe: nunca
                # usarlo como teléfono del remitente.
                real = ""
                alt = str(key.get("remoteJidAlt") or "")
                if alt.endswith("@s.whatsapp.net"):
                    real = alt.split("@", 1)[0]
                if not real:
                    sender = str(payload.get("sender") or "")
                    if sender.endswith("@s.whatsapp.net"):
                        real = sender.split("@", 1)[0]
                if real:
                    wa_lid = remote_jid
                    wa_id = real
                else:
                    # Número oculto de verdad: la persona SOLO existe como
                    # LID. Se conserva el JID completo («...@lid») como
                    # identificador: así el bot la reconoce siempre como el
                    # mismo contacto y puede responderle (Evolution acepta un
                    # JID completo en el campo «number»). Con solo los dígitos
                    # parecería un teléfono inexistente y la respuesta se
                    # perdería.
                    wa_id = remote_jid
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
            # No loguear el payload completo (contiene teléfono, nombre, texto del mensaje = PII)
            logger.debug("Error parseando payload de Evolution: %s (tipo: %s)", e, type(e).__name__)
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
        """Envía texto vía POST /message/sendText/{instance}. Devuelve el id.

        Reintenta una vez ante errores de conexión transitorios: Evolution
        puede tener micro-consultas de red bajo carga (Baileys/Docker).
        """
        settings = self._settings()
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
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
            except (httpx.ConnectError, httpx.ConnectTimeout,
                    httpx.ReadTimeout) as e:
                last_error = e
                if attempt == 1:
                    logger.warning(
                        "[EvolutionChannel] Conexión fallida (intento 1), "
                        "reintentando: %s", e,
                    )
                    import asyncio

                    await asyncio.sleep(2)
                # El segundo intento falló → que el llamador lo maneje
        raise last_error  # type: ignore[misc]

    async def send_document(
        self, to: str, file_name: str, content_base64: str, mimetype: str
    ) -> str | None:
        """Envía un documento base64 vía POST /message/sendMedia/{instance}.

        Si es AUDIO (respuestas de voz del asistente), se manda como nota
        de voz y no como un archivo adjunto.
        """
        if mimetype.lower().startswith("audio/"):
            return await self.send_voice(to, content_base64)

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

    async def send_voice(self, to: str, audio_base64: str) -> str | None:
        """Envía una NOTA DE VOZ (la burbuja con onda, no un archivo adjunto).

        POST /message/sendWhatsAppAudio/{instance}. «encoding» pide a
        Evolution convertir el audio a OGG/Opus, el formato de las notas de
        voz de WhatsApp.
        """
        settings = self._settings()
        async with self._client() as client:
            response = await client.post(
                f"/message/sendWhatsAppAudio/{settings.evolution_instance}",
                json={"number": to, "audio": audio_base64, "encoding": True},
            )
            response.raise_for_status()
            data = response.json()
            message_id = (
                (data.get("key") or {}).get("id")
                or (data.get("message") or {}).get("id")
            )
            logger.debug(
                "[EvolutionChannel] Nota de voz enviada a %s (id %s)", to, message_id
            )
            return message_id

    # ── Media entrante ──────────────────────────────────────────────────────

    async def fetch_media_base64(
        self, message_id: str, *, raw_payload: dict[str, Any] | None = None
    ) -> str | None:
        """Descarga y descifra la media de un mensaje (audio, imagen, doc).

        Las URL de WhatsApp (mmg.whatsapp.net) vienen CIFRADAS: bajarlas con
        un GET entrega bytes inservibles. Evolution las descifra con
        POST /chat/getBase64FromMediaMessage/{instance}. Devuelve el base64
        puro (sin prefijo data:) o None si no se pudo.
        """
        settings = self._settings()
        message_payload: dict[str, Any] = {"key": {"id": message_id}}
        if raw_payload:
            data = raw_payload.get("data") or {}
            key = data.get("key") or {}
            message = data.get("message") or {}
            if key and message:
                # Evolution needs the encrypted media metadata and the
                # original message to decrypt WhatsApp media.
                message_payload = {"key": key, "message": message}

        try:
            async with self._client() as client:
                response = await client.post(
                    f"/chat/getBase64FromMediaMessage/{settings.evolution_instance}",
                    json={"message": message_payload, "convertToMp4": False},
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "[EvolutionChannel] No se pudo descargar la media %s: %s",
                message_id,
                exc,
            )
            return None

        b64 = data.get("base64") if isinstance(data, dict) else None
        if not b64:
            return None
        if b64.startswith("data:") and "," in b64:
            b64 = b64.split(",", 1)[1]
        return b64

    # ── Estado de conexión (usado por el router /whatsapp del panel) ────────

    @staticmethod
    def _to_jid(number: str) -> str:
        """Número → JID de chat directo (necesario para read/presence)."""
        if "@" in number:
            return number
        return f"{number}@s.whatsapp.net"

    async def mark_read(self, to: str, message_id: str) -> None:
        """Check azul: POST /chat/markMessageAsRead/{instance}.

        Anti-detección de Meta: el bot SIEMPRE lee antes de responder.
        """
        settings = self._settings()
        async with self._client() as client:
            response = await client.post(
                f"/chat/markMessageAsRead/{settings.evolution_instance}",
                json={
                    "readMessages": [
                        {
                            "remoteJid": self._to_jid(to),
                            "fromMe": False,
                            "id": message_id,
                        }
                    ]
                },
            )
            if response.status_code >= 400:
                # No es crítico: un check azul fallido no rompe la respuesta
                logger.warning(
                    "[EvolutionChannel] mark_read %s falló: HTTP %s",
                    message_id,
                    response.status_code,
                )
                return
            logger.debug("[EvolutionChannel] Mensaje %s marcado como leído", message_id)

    async def send_typing(self, to: str, *, composing: bool = True) -> None:
        """«escribiendo…» / detener: POST /chat/sendPresence/{instance}."""
        settings = self._settings()
        async with self._client() as client:
            response = await client.post(
                f"/chat/sendPresence/{settings.evolution_instance}",
                json={
                    "number": to,
                    "presence": "composing" if composing else "paused",
                },
            )
            if response.status_code >= 400:
                logger.warning(
                    "[EvolutionChannel] sendPresence(%s) falló: HTTP %s",
                    composing,
                    response.status_code,
                )

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

    async def send_buttons(
        self, to: str, text: str, buttons: list[dict[str, str]], footer: str | None = None
    ) -> str | None:
        """Envía mensaje con botones de respuesta (reply buttons) via Evolution API.
        
        buttons: lista de dicts con keys 'id' y 'title' (máx 3).
        footer: texto opcional al pie.
        """
        if len(buttons) > 3:
            raise ValueError("WhatsApp permite máximo 3 botones")
        
        settings = self._settings()
        async with self._client() as client:
            response = await client.post(
                f"/message/sendButtons/{settings.evolution_instance}",
                json={
                    "number": to,
                    "text": text,
                    "buttons": [
                        {"buttonId": b["id"], "buttonText": {"displayText": b["title"]}, "type": 1}
                        for b in buttons
                    ],
                    "footer": footer or "",
                },
            )
            response.raise_for_status()
            data = response.json()
            message_id = (
                (data.get("key") or {}).get("id")
                or (data.get("message") or {}).get("id")
            )
            logger.debug(
                "[EvolutionChannel] Botones enviados a %s (id %s)", to, message_id
            )
            return message_id

    async def send_list(
        self, to: str, text: str, button_text: str, sections: list[dict], title: str | None = None
    ) -> str | None:
        """Envía mensaje con lista (list message) via Evolution API.
        
        sections: lista de dicts con 'title' y 'rows' (cada row con 'id', 'title', 'description').
        button_text: texto del botón que abre la lista.
        title: título opcional de la lista.
        """
        settings = self._settings()
        async with self._client() as client:
            response = await client.post(
                f"/message/sendList/{settings.evolution_instance}",
                json={
                    "number": to,
                    "text": text,
                    "buttonText": button_text,
                    "title": title or "",
                    "sections": sections,
                },
            )
            response.raise_for_status()
            data = response.json()
            message_id = (
                (data.get("key") or {}).get("id")
                or (data.get("message") or {}).get("id")
            )
            logger.debug(
                "[EvolutionChannel] Lista enviada a %s (id %s)", to, message_id
            )
            return message_id

    async def send_poll(
        self, to: str, question: str, options: list[str]
    ) -> str | None:
        """Envía una encuesta (poll) via Evolution API.
        
        options: lista de opciones (máx 12, min 2).
        """
        if len(options) < 2 or len(options) > 12:
            raise ValueError("WhatsApp permite entre 2 y 12 opciones en encuesta")
        
        settings = self._settings()
        async with self._client() as client:
            response = await client.post(
                f"/message/sendPoll/{settings.evolution_instance}",
                json={
                    "number": to,
                    "name": question,
                    "values": options,
                    "selectableCount": 1,
                },
            )
            response.raise_for_status()
            data = response.json()
            message_id = (
                (data.get("key") or {}).get("id")
                or (data.get("message") or {}).get("id")
            )
            logger.debug(
                "[EvolutionChannel] Encuesta enviada a %s (id %s)", to, message_id
            )
            return message_id
