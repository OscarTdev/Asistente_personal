"""Audio: transcripción (STT) y síntesis de voz (TTS).

Proveedores configurables vía env: cualquier endpoint compatible con
OpenAI sirve (Groq para STT es gratis y rápido; OpenAI para TTS).

STT: POST /audio/transcriptions (multipart, Whisper large-v3)
TTS: POST /audio/speech (JSON, devuelve audio MP3)

Cifras, direcciones y confirmaciones SIEMPRE van también en texto,
aunque la respuesta sea de audio (spec §12).
"""

import base64
import logging
import re
from abc import ABC, abstractmethod

import httpx

logger = logging.getLogger(__name__)

# Máscara de datos sensibles antes de sintetizar (spec §12)
_MASK_PATTERNS = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "[correo]"),
    (re.compile(r"\b\d{6,20}\b"), "[número]"),
]


def mask_for_speech(text: str) -> str:
    """Enmascara documentos, correos y números largos antes de TTS."""
    result = text
    for pattern, replacement in _MASK_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def audio_file_for_upload(audio_bytes: bytes) -> tuple[str, str]:
    """(nombre, tipo MIME) según la firma real del audio.

    Las notas de voz de WhatsApp son OGG/Opus. Etiquetarlas como WAV (lo
    que se hacía antes) puede hacer que el proveedor rechace el archivo.
    """
    head = audio_bytes[:12]
    if head.startswith(b"OggS"):
        return "audio.ogg", "audio/ogg"
    if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio.mp3", "audio/mpeg"
    if head[:4] == b"RIFF":
        return "audio.wav", "audio/wav"
    if head[4:8] == b"ftyp":
        return "audio.m4a", "audio/mp4"
    if head.startswith(b"\x1aE\xdf\xa3"):
        return "audio.webm", "audio/webm"
    return "audio.ogg", "audio/ogg"  # formato habitual de WhatsApp


class STTProvider(ABC):
    """Interfaz de transcripción de voz a texto."""

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, *, language: str = "es") -> str:
        """Transcribe audio y devuelve el texto."""
        ...


class TTSProvider(ABC):
    """Interfaz de síntesis de texto a voz."""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Convierte texto en audio (MP3) listo para enviar."""
        ...


class OpenAISTT(STTProvider):
    """Transcripción con cualquier endpoint compatible (Groq, OpenAI, etc.)."""

    def __init__(self, *, api_key: str, base_url: str, model: str = "whisper-large-v3"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def transcribe(self, audio_bytes: bytes, *, language: str = "es") -> str:
        file_name, mime = audio_file_for_upload(audio_bytes)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={"file": (file_name, audio_bytes, mime)},
                data={"model": self.model, "language": language},
            )
            response.raise_for_status()
            return (response.json().get("text") or "").strip()


class OpenAITTS(TTSProvider):
    """Síntesis con cualquier endpoint compatible (OpenAI, etc.)."""

    def __init__(self, *, api_key: str, base_url: str, model: str = "tts-1", voice: str = "alloy"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.voice = voice

    async def synthesize(self, text: str) -> bytes:
        cleaned = mask_for_speech(text)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": cleaned,
                    "voice": self.voice,
                    "response_format": "mp3",
                },
            )
            response.raise_for_status()
            return response.content


class EdgeTTS(TTSProvider):
    """Síntesis con la voz de Microsoft Edge — 100% gratis, sin API key.

    Usa las voces neuronales de Edge (las mismas del navegador) a través
    del servicio de Microsoft. Voz colombiana: es-CO-ElenaNeural.
    """

    def __init__(self, voice: str = "es-CO-SalomeNeural"):
        self.voice = voice

    async def synthesize(self, text: str) -> bytes:
        import edge_tts

        cleaned = mask_for_speech(text)
        communicate = edge_tts.Communicate(cleaned, self.voice)
        audio_chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
        return b"".join(audio_chunks)


def get_stt_provider():
    """Devuelve el proveedor STT configurado o None si no hay API key."""
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.stt_api_key:
        return None
    return OpenAISTT(
        api_key=settings.stt_api_key,
        base_url=settings.stt_base_url,
        model=settings.stt_model,
    )


def get_tts_provider():
    """Devuelve el proveedor TTS configurado o None.

    Prioridad: TTS_API_KEY → EdgeTTS (gratis, sin API key).
    """
    from app.core.config import get_settings

    settings = get_settings()
    if settings.tts_api_key:
        return OpenAITTS(
            api_key=settings.tts_api_key,
            base_url=settings.tts_base_url,
            model=settings.tts_model,
            voice=settings.tts_voice,
        )
    # Edge TTS: gratis, sin API key — el default
    return EdgeTTS(voice=settings.tts_voice)


async def transcribe_audio_message(media_base64: str, *, language: str = "es") -> str:
    """Transcribe un mensaje de audio base64 y devuelve el texto.

    Si no hay proveedor STT configurado, devuelve cadena vacía (el
    orquestador responde pidiendo el detalle por escrito).
    """
    provider = get_stt_provider()
    if provider is None:
        logger.warning(
            "STT_API_KEY no configurada: los audios no se pueden transcribir"
        )
        return ""

    try:
        audio_bytes = base64.b64decode(media_base64)
        text = await provider.transcribe(audio_bytes, language=language)
        if text:
            logger.debug("Audio transcrito: %s caracteres", len(text))
        return text
    except Exception:
        logger.exception("Error transcribiendo audio")
        return ""
