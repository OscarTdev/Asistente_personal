from typing import Any, Literal

from pydantic import BaseModel, Field


class IncomingMessage(BaseModel):
    channel_message_id: str  # WhatsApp message id (clave de dedupe)
    wa_id: str               # teléfono del remitente, solo dígitos
    wa_lid: str | None = None  # LID de WhatsApp si el chat llegó con él
    push_name: str | None = None
    message_type: Literal["text", "audio", "image", "document", "unsupported"] = "text"
    text: str | None = None  # texto, o caption si es media
    from_me: bool = False    # mensaje enviado desde el propio número del bot
    media_url: str | None = None
    media_base64: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
