import json

import httpx
import pytest

from app.channels.base import ChannelParseError
from app.channels.evolution import EvolutionChannel
from app.schemas.channel import IncomingMessage


def _mock_client(channel: EvolutionChannel, monkeypatch, handler) -> None:
    """Sustituye el cliente httpx del canal por un transporte simulado."""
    monkeypatch.setattr(
        channel,
        "_client",
        lambda: httpx.AsyncClient(
            base_url="http://test-evolution:8080",
            headers={"apikey": "test-key"},
            transport=httpx.MockTransport(handler),
        ),
    )


@pytest.mark.asyncio
async def test_parse_conversation_text_message():
    """Payload con message.conversation (messageType "conversation") → texto."""
    payload = {
        "event": "messages.upsert",
        "instance": "auratest",
        "data": {
            "key": {
                "id": "3EB0F9B1B5D6C7D8",
                "remoteJid": "573001234567@s.whatsapp.net",
                "fromMe": False,
            },
            "pushName": "Juan Pérez",
            "messageType": "conversation",
            "message": {
                "conversation": "Hola, necesito una cotización para un tablero",
            },
            "status": "RECEIVED",
        },
    }

    result = await EvolutionChannel().parse_incoming(payload)

    assert isinstance(result, IncomingMessage)
    assert result.channel_message_id == "3EB0F9B1B5D6C7D8"
    assert result.wa_id == "573001234567"
    assert result.push_name == "Juan Pérez"
    assert result.message_type == "text"
    assert result.text == "Hola, necesito una cotización para un tablero"
    assert result.raw == payload


@pytest.mark.asyncio
async def test_parse_extended_text_message():
    """Payload con extendedTextMessage.text → texto (normalizado a "text")."""
    payload = {
        "event": "messages.upsert",
        "instance": "auratest",
        "data": {
            "key": {
                "id": "3EB0F9B1B5D6C7D9",
                "remoteJid": "573001234567@s.whatsapp.net",
                "fromMe": False,
            },
            "pushName": "María López",
            "messageType": "extendedTextMessage",
            "message": {
                "extendedTextMessage": {
                    "text": "Mensaje extendido de prueba",
                }
            },
            "status": "RECEIVED",
        },
    }

    result = await EvolutionChannel().parse_incoming(payload)

    assert isinstance(result, IncomingMessage)
    assert result.channel_message_id == "3EB0F9B1B5D6C7D9"
    assert result.wa_id == "573001234567"
    assert result.push_name == "María López"
    assert result.message_type == "text"
    assert result.text == "Mensaje extendido de prueba"
    assert result.raw == payload


@pytest.mark.asyncio
async def test_parse_missing_key_id():
    """Sin data.key.id → ChannelParseError."""
    payload = {
        "event": "messages.upsert",
        "instance": "auratest",
        "data": {
            "key": {
                "remoteJid": "573001234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {"conversation": "Hola"},
        },
    }

    with pytest.raises(ChannelParseError):
        await EvolutionChannel().parse_incoming(payload)


@pytest.mark.asyncio
async def test_parse_missing_remote_jid():
    """Sin data.key.remoteJid → ChannelParseError."""
    payload = {
        "event": "messages.upsert",
        "instance": "auratest",
        "data": {
            "key": {
                "id": "3EB0F9B1B5D6C7D8",
                "fromMe": False,
            },
            "message": {"conversation": "Hola"},
        },
    }

    with pytest.raises(ChannelParseError):
        await EvolutionChannel().parse_incoming(payload)


@pytest.mark.asyncio
async def test_parse_missing_message():
    """Sin data.message → ChannelParseError."""
    payload = {
        "event": "messages.upsert",
        "instance": "auratest",
        "data": {
            "key": {
                "id": "3EB0F9B1B5D6C7D8",
                "remoteJid": "573001234567@s.whatsapp.net",
                "fromMe": False,
            },
        },
    }

    with pytest.raises(ChannelParseError):
        await EvolutionChannel().parse_incoming(payload)


@pytest.mark.asyncio
async def test_parse_audio_message():
    """Fase B: el audio se parsea como type "audio" con su URL de media."""
    payload = {
        "event": "messages.upsert",
        "instance": "auratest",
        "data": {
            "key": {
                "id": "3EB0F9B1B5D6C7DA",
                "remoteJid": "573001234567@s.whatsapp.net",
                "fromMe": False,
            },
            "messageType": "audioMessage",
            "message": {"audioMessage": {"url": "https://example.com/audio.ogg"}},
        },
    }

    result = await EvolutionChannel().parse_incoming(payload)

    assert isinstance(result, IncomingMessage)
    assert result.message_type == "audio"
    assert result.media_url == "https://example.com/audio.ogg"
    assert result.text is None


@pytest.mark.asyncio
async def test_parse_image_message_with_caption():
    """Imagen con caption → type "image", texto = caption, base64 presente."""
    payload = {
        "event": "messages.upsert",
        "instance": "auratest",
        "data": {
            "key": {
                "id": "3EB0F9B1B5D6C7DB",
                "remoteJid": "573001234567@s.whatsapp.net",
                "fromMe": False,
            },
            "messageType": "imageMessage",
            "message": {
                "imageMessage": {
                    "url": "https://example.com/img.jpg",
                    "caption": "Así quedó la instalación",
                    "base64": "aGVsbG8=",
                }
            },
        },
    }

    result = await EvolutionChannel().parse_incoming(payload)

    assert result.message_type == "image"
    assert result.text == "Así quedó la instalación"
    assert result.media_url == "https://example.com/img.jpg"
    assert result.media_base64 == "aGVsbG8="


@pytest.mark.asyncio
async def test_parse_self_message_returns_flag():
    """fromMe ya no se descarta en el canal: la ingesta decide.

    El auto-chat ("mensaje a ti mismo") del dueño es una conversación
    válida con su asistente cuando el bot corre en su propio número.
    """
    payload = {
        "event": "messages.upsert",
        "instance": "auratest",
        "data": {
            "key": {
                "id": "3EB0F9B1B5D6C7DC",
                "remoteJid": "573001234567@s.whatsapp.net",
                "fromMe": True,
            },
            "message": {"conversation": "nota para mí mismo"},
        },
    }

    result = await EvolutionChannel().parse_incoming(payload)

    assert result.from_me is True
    assert result.wa_id == "573001234567"


@pytest.mark.asyncio
async def test_send_text_calls_evolution(monkeypatch: pytest.MonkeyPatch):
    """send_text llama a /message/sendText/{instance} con número y texto."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["apikey"] = request.headers.get("apikey")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"id": "x"}})

    channel = EvolutionChannel()
    _mock_client(channel, monkeypatch, handler)

    await channel.send_text(to="573001234567", text="Hola desde Aura")

    assert "/message/sendText/" in captured["url"]
    assert captured["url"].endswith("/instance") or "aura" in captured["url"]
    assert captured["apikey"] == "test-key"
    assert captured["body"]["number"] == "573001234567"
    assert captured["body"]["text"] == "Hola desde Aura"


# ── Números ocultos (LID): usuarios de WhatsApp con @nombre de usuario ─────


@pytest.mark.asyncio
async def test_parse_lid_message_resolves_real_number():
    """Chats con LID: el teléfono real llega en el sobre del webhook (sender)."""
    payload = {
        "event": "messages.upsert",
        "instance": "aura",
        "data": {
            "key": {
                "id": "AC7F4DB89E176E859398A7F55DD63A94",
                "remoteJid": "137314785341477@lid",
                "remoteJidAlt": None,
                "fromMe": False,
                "addressingMode": "lid",
            },
            "pushName": "Niurka",
            "messageType": "conversation",
            "message": {"conversation": "Hola"},
        },
        "sender": "573043223100@s.whatsapp.net",
    }

    result = await EvolutionChannel().parse_incoming(payload)

    assert result.wa_id == "573043223100"
    # El LID queda como alias con su JID completo (misma forma que se usa
    # cuando la persona solo existe como LID → se puede enlazar después)
    assert result.wa_lid == "137314785341477@lid"
    assert result.push_name == "Niurka"


@pytest.mark.asyncio
async def test_parse_lid_without_real_number_keeps_full_jid():
    """Número oculto sin teléfono: el JID completo («...@lid») es la identidad.

    Con solo los dígitos parecería un teléfono inexistente y la respuesta
    del bot se perdería; con el JID completo Evolution sí puede responder.
    """
    payload = {
        "event": "messages.upsert",
        "instance": "aura",
        "data": {
            "key": {
                "id": "3EB0LID0000000001",
                "remoteJid": "137314785341477@lid",
                "fromMe": False,
            },
            "message": {"conversation": "Hola"},
        },
    }

    result = await EvolutionChannel().parse_incoming(payload)

    assert result.wa_id == "137314785341477@lid"
    assert result.wa_lid is None


@pytest.mark.asyncio
async def test_parse_lid_falls_back_to_remote_jid_alt():
    """remoteJidAlt con el JID real también resuelve el teléfono."""
    payload = {
        "event": "messages.upsert",
        "instance": "aura",
        "data": {
            "key": {
                "id": "3EB0LID0000000002",
                "remoteJid": "137314785341477@lid",
                "remoteJidAlt": "573043223100@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {"conversation": "Hola"},
        },
    }

    result = await EvolutionChannel().parse_incoming(payload)

    assert result.wa_id == "573043223100"
    assert result.wa_lid == "137314785341477@lid"


@pytest.mark.asyncio
async def test_send_text_to_lid_jid_passes_full_jid(monkeypatch: pytest.MonkeyPatch):
    """Responder a un número oculto envía el JID completo a Evolution."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"key": {"id": "z"}})

    channel = EvolutionChannel()
    _mock_client(channel, monkeypatch, handler)

    await channel.send_text(to="137314785341477@lid", text="Hola")

    assert captured["body"]["number"] == "137314785341477@lid"


# ── Documentos, voz y media ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_document_calls_send_media(monkeypatch: pytest.MonkeyPatch):
    """send_document llama a /message/sendMedia/{instance} con el base64."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"id": "y"}})

    channel = EvolutionChannel()
    _mock_client(channel, monkeypatch, handler)

    await channel.send_document(
        to="573001234567",
        file_name="cotizacion_ab12.pdf",
        content_base64="cGRm",
        mimetype="application/pdf",
    )

    assert "/message/sendMedia/" in captured["url"]
    assert captured["body"]["mediatype"] == "document"
    assert captured["body"]["fileName"] == "cotizacion_ab12.pdf"
    assert captured["body"]["media"] == "cGRm"


@pytest.mark.asyncio
async def test_send_voice_uses_whatsapp_audio_endpoint(
    monkeypatch: pytest.MonkeyPatch,
):
    """La respuesta de voz es una NOTA DE VOZ, no un archivo adjunto."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"key": {"id": "voz1"}})

    channel = EvolutionChannel()
    _mock_client(channel, monkeypatch, handler)

    message_id = await channel.send_voice("573001234567", "QVVESU8=")

    assert "/message/sendWhatsAppAudio/" in captured["url"]
    assert captured["body"]["number"] == "573001234567"
    assert captured["body"]["audio"] == "QVVESU8="
    assert captured["body"]["encoding"] is True
    assert message_id == "voz1"


@pytest.mark.asyncio
async def test_fetch_media_base64_decrypts_via_evolution(
    monkeypatch: pytest.MonkeyPatch,
):
    """La media se pide a Evolution (la URL de WhatsApp viene cifrada)."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"mediaType": "audioMessage", "base64": "T0dHUw=="}
        )

    channel = EvolutionChannel()
    _mock_client(channel, monkeypatch, handler)

    result = await channel.fetch_media_base64("3EB0AUDIO")

    assert "/chat/getBase64FromMediaMessage/" in captured["url"]
    assert captured["body"]["message"]["key"]["id"] == "3EB0AUDIO"
    assert result == "T0dHUw=="


@pytest.mark.asyncio
async def test_fetch_media_base64_sends_original_media_message(
    monkeypatch: pytest.MonkeyPatch,
):
    """La API necesita la metadata cifrada original para descifrar imágenes."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"base64": "aW1hZ2U="})

    channel = EvolutionChannel()
    _mock_client(channel, monkeypatch, handler)
    raw_payload = {
        "data": {
            "key": {"id": "IMAGE-MEDIA", "remoteJid": "573001234567@s.whatsapp.net"},
            "message": {"imageMessage": {"url": "https://mmg.whatsapp.net/image"}},
        }
    }

    result = await channel.fetch_media_base64("IMAGE-MEDIA", raw_payload=raw_payload)

    assert captured["body"]["message"] == raw_payload["data"]
    assert result == "aW1hZ2U="


@pytest.mark.asyncio
async def test_fetch_media_base64_strips_data_uri_prefix(
    monkeypatch: pytest.MonkeyPatch,
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"base64": "data:audio/ogg;base64,T0dHUw=="}
        )

    channel = EvolutionChannel()
    _mock_client(channel, monkeypatch, handler)

    assert await channel.fetch_media_base64("x") == "T0dHUw=="


@pytest.mark.asyncio
async def test_fetch_media_base64_returns_none_on_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    channel = EvolutionChannel()
    _mock_client(channel, monkeypatch, handler)

    assert await channel.fetch_media_base64("x") is None


@pytest.mark.asyncio
async def test_disconnect_calls_logout(monkeypatch: pytest.MonkeyPatch):
    """disconnect llama a DELETE /instance/logout/{instance}."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "status": "SUCCESS",
                "error": False,
                "response": {"message": "Instance logged out"},
            },
        )

    channel = EvolutionChannel()
    _mock_client(channel, monkeypatch, handler)

    result = await channel.disconnect()

    assert captured["method"] == "DELETE"
    assert "/instance/logout/" in captured["url"]
    assert result["status"] == "SUCCESS"
