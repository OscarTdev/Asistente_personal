from typing import Any, Literal

from pydantic import BaseModel, Field


class IncomingMessage(BaseModel):
    channel_message_id: str  # WhatsApp message id (clave de dedupe)
    wa_id: str               # teléfono del remitente, solo dígitos
    push_name: str | None = None
    message_type: Literal["text", "audio", "image", "document"] = "text"
    text: str | None = None  # solo para message_type == "text"
    raw: dict[str, Any] = Field(default_factory=dict)
