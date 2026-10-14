import json

import pytest

from app.channels.base import ChannelParseError
from app.channels.evolution import EvolutionChannel
from app.schemas.channel import IncomingMessage


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
    import httpx

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["apikey"] = request.headers.get("apikey")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"id": "x"}})

    channel = EvolutionChannel()
    monkeypatch.setattr(
        channel,
        "_client",
        lambda: httpx.AsyncClient(
            base_url="http://test-evolution:8080",
            headers={"apikey": "test-key"},
            transport=httpx.MockTransport(handler),
        ),
    )

    await channel.send_text(to="573001234567", text="Hola desde Aura")

    assert "/message/sendText/" in captured["url"]
    assert captured["url"].endswith("/instance") or "aura" in captured["url"]
    assert captured["apikey"] == "test-key"
    assert captured["body"]["number"] == "573001234567"
    assert captured["body"]["text"] == "Hola desde Aura"


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
    assert result.wa_lid == "137314785341477"
    assert result.push_name == "Niurka"


@pytest.mark.asyncio
async def test_parse_lid_without_real_number_keeps_lid():
    """Sin sender ni remoteJidAlt: el LID queda como wa_id (el mensaje no se pierde)."""
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

    assert result.wa_id == "137314785341477"
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
    assert result.wa_lid == "137314785341477"


@pytest.mark.asyncio
async def test_send_document_calls_send_media(monkeypatch: pytest.MonkeyPatch):
    """send_document llama a /message/sendMedia/{instance} con el base64."""
    import httpx

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"id": "y"}})

    channel = EvolutionChannel()
    monkeypatch.setattr(
        channel,
        "_client",
        lambda: httpx.AsyncClient(
            base_url="http://test-evolution:8080",
            headers={"apikey": "test-key"},
            transport=httpx.MockTransport(handler),
        ),
    )

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
async def test_disconnect_calls_logout(monkeypatch: pytest.MonkeyPatch):
    """disconnect llama a DELETE /instance/logout/{instance}."""
    import httpx

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
    monkeypatch.setattr(
        channel,
        "_client",
        lambda: httpx.AsyncClient(
            base_url="http://test-evolution:8080",
            headers={"apikey": "test-key"},
            transport=httpx.MockTransport(handler),
        ),
    )

    result = await channel.disconnect()

    assert captured["method"] == "DELETE"
    assert "/instance/logout/" in captured["url"]
    assert result["status"] == "SUCCESS"
