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
async def test_parse_audio_message_has_no_text():
    """Audio (sin texto extraíble en F1) → ChannelParseError → 400."""
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

    with pytest.raises(ChannelParseError):
        await EvolutionChannel().parse_incoming(payload)


@pytest.mark.asyncio
async def test_send_text_stub():
    """send_text es un stub que no lanza error."""
    await EvolutionChannel().send_text(to="573001234567", text="Hola")
