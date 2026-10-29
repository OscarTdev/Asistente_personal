"""Media y números ocultos en la ingesta del webhook.

- Un usuario de WhatsApp con @nombre de usuario llega solo como LID: el bot
  debe reconocerlo como contacto y poder responderle.
- Las notas de voz se transcriben y las imágenes se describen: el contenido
  del mensaje queda como texto para el asistente.
"""

from http import HTTPStatus

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import Contact, Message, Tenant
from app.services import audio as audio_service
from app.services import vision as vision_service
from app.services.audio import audio_file_for_upload
from app.services.vision import guess_image_mime


def _payload(message_id: str, remote_jid: str, message: dict, **extra) -> dict:
    return {
        "event": "messages.upsert",
        "instance": "auratest",
        "data": {
            "key": {"id": message_id, "remoteJid": remote_jid, "fromMe": False},
            "pushName": "Prueba",
            "message": message,
        },
        **extra,
    }


async def _stored_message(db_session, message_id: str) -> Message:
    return (
        await db_session.execute(
            select(Message).where(Message.whatsapp_message_id == message_id)
        )
    ).scalar_one()


# ── Formatos ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (b"OggS\x00\x02" + b"\x00" * 10, "audio.ogg"),
        (b"ID3\x04" + b"\x00" * 10, "audio.mp3"),
        (b"RIFF\x00\x00\x00\x00WAVE", "audio.wav"),
        (b"\x00\x00\x00\x18ftypM4A ", "audio.m4a"),
        (b"\x1aE\xdf\xa3" + b"\x00" * 10, "audio.webm"),
        (b"\x00\x01\x02\x03" * 4, "audio.ogg"),  # desconocido → formato de WhatsApp
    ],
)
def test_audio_file_for_upload_detects_format(head, expected):
    name, _mime = audio_file_for_upload(head)
    assert name == expected


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, "image/png"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
        (b"GIF89a" + b"\x00" * 8, "image/gif"),
        (b"\xff\xd8\xff\xe0" + b"\x00" * 8, "image/jpeg"),
        (b"\x00" * 12, "image/jpeg"),
    ],
)
def test_guess_image_mime(head, expected):
    assert guess_image_mime(head) == expected


# ── Número oculto (LID) ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hidden_number_sender_is_recognized_as_contact(
    client: AsyncClient, tenant: Tenant, db_session, webhook_headers: dict
):
    """Quien llega solo como LID queda como contacto con su JID completo."""
    payload = _payload(
        "LIDONLY0001", "137314785341477@lid", {"conversation": "Hola"}
    )

    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=webhook_headers, json=payload
    )

    assert response.status_code == HTTPStatus.OK
    contact = (
        await db_session.execute(
            select(Contact).where(Contact.wa_id == "137314785341477@lid")
        )
    ).scalar_one()
    assert contact.is_active


@pytest.mark.asyncio
async def test_hidden_number_second_message_same_contact(
    client: AsyncClient, tenant: Tenant, db_session, webhook_headers: dict
):
    """Dos mensajes del mismo número oculto → un solo contacto (no duplica)."""
    for message_id in ("LIDONLY0002", "LIDONLY0003"):
        response = await client.post(
            "/api/v1/webhooks/whatsapp",
            headers=webhook_headers,
            json=_payload(message_id, "222000111@lid", {"conversation": "Hola"}),
        )
        assert response.status_code == HTTPStatus.OK

    contacts = (
        (
            await db_session.execute(
                select(Contact).where(Contact.wa_id == "222000111@lid")
            )
        )
        .scalars()
        .all()
    )
    assert len(contacts) == 1


# ── Audio e imágenes ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audio_is_transcribed_into_message_content(
    client: AsyncClient,
    tenant: Tenant,
    db_session,
    webhook_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_transcribe(media_base64: str, *, language: str = "es") -> str:
        assert media_base64 == "T2dnUw=="
        return "cotízame tres tomacorrientes"

    monkeypatch.setattr(audio_service, "transcribe_audio_message", fake_transcribe)
    payload = _payload(
        "AUDIO000001",
        "573001234567@s.whatsapp.net",
        {"audioMessage": {"url": "https://example.com/a.enc", "base64": "T2dnUw=="}},
    )

    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=webhook_headers, json=payload
    )

    assert response.status_code == HTTPStatus.OK
    stored = await _stored_message(db_session, "AUDIO000001")
    assert stored.type == "audio"
    assert stored.content == "cotízame tres tomacorrientes"


@pytest.mark.asyncio
async def test_audio_without_stt_keeps_empty_content(
    client: AsyncClient,
    tenant: Tenant,
    db_session,
    webhook_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """Sin transcripción disponible el mensaje se guarda igual (sin romper)."""

    async def fake_transcribe(media_base64: str, *, language: str = "es") -> str:
        return ""

    monkeypatch.setattr(audio_service, "transcribe_audio_message", fake_transcribe)
    payload = _payload(
        "AUDIO000002",
        "573001234567@s.whatsapp.net",
        {"audioMessage": {"base64": "T2dnUw=="}},
    )

    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=webhook_headers, json=payload
    )

    assert response.status_code == HTTPStatus.OK
    stored = await _stored_message(db_session, "AUDIO000002")
    assert not stored.content


@pytest.mark.asyncio
async def test_image_is_described_when_vision_enabled(
    client: AsyncClient,
    tenant: Tenant,
    db_session,
    webhook_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_describe(image_base64: str, *, caption: str | None = None) -> str:
        assert caption == "mira este tablero"
        return "Tablero eléctrico con dos breakers quemados."

    monkeypatch.setattr(vision_service, "vision_enabled", lambda: True)
    monkeypatch.setattr(vision_service, "describe_image", fake_describe)
    payload = _payload(
        "IMAGE000001",
        "573001234567@s.whatsapp.net",
        {"imageMessage": {"caption": "mira este tablero", "base64": "/9j/4AAQ"}},
    )

    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=webhook_headers, json=payload
    )

    assert response.status_code == HTTPStatus.OK
    stored = await _stored_message(db_session, "IMAGE000001")
    assert "mira este tablero" in stored.content
    assert "breakers quemados" in stored.content


@pytest.mark.asyncio
async def test_image_without_vision_keeps_only_caption(
    client: AsyncClient,
    tenant: Tenant,
    db_session,
    webhook_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(vision_service, "vision_enabled", lambda: False)
    payload = _payload(
        "IMAGE000002",
        "573001234567@s.whatsapp.net",
        {"imageMessage": {"caption": "solo texto", "base64": "/9j/4AAQ"}},
    )

    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=webhook_headers, json=payload
    )

    assert response.status_code == HTTPStatus.OK
    stored = await _stored_message(db_session, "IMAGE000002")
    assert stored.content == "solo texto"
