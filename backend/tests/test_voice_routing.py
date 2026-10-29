"""Las respuestas de voz del asistente salen como NOTA DE VOZ de WhatsApp."""

import json

import httpx
import pytest

from app.channels.evolution import EvolutionChannel


def _mock_client(channel: EvolutionChannel, monkeypatch, handler) -> None:
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
async def test_audio_document_is_sent_as_voice_note(monkeypatch: pytest.MonkeyPatch):
    """send_document con audio/mpeg → sendWhatsAppAudio, no sendMedia."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"key": {"id": "voz-1"}})

    channel = EvolutionChannel()
    _mock_client(channel, monkeypatch, handler)

    message_id = await channel.send_document(
        "573001234567", "respuesta_ab12.mp3", "TVAz", "audio/mpeg"
    )

    assert "/message/sendWhatsAppAudio/" in captured["url"]
    assert "/message/sendMedia/" not in captured["url"]
    assert captured["body"]["audio"] == "TVAz"
    assert message_id == "voz-1"


@pytest.mark.asyncio
async def test_pdf_document_still_uses_send_media(monkeypatch: pytest.MonkeyPatch):
    """Los PDF (cotizaciones, informes) siguen enviándose como documento."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"key": {"id": "doc-1"}})

    channel = EvolutionChannel()
    _mock_client(channel, monkeypatch, handler)

    await channel.send_document(
        "573001234567", "COT-0001.pdf", "cGRm", "application/pdf"
    )

    assert "/message/sendMedia/" in captured["url"]
