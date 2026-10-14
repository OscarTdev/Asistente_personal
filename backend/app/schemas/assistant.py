"""Esquemas del asistente del dueño (router de intenciones)."""

from typing import Literal

from pydantic import BaseModel, Field


class AssistantIntent(BaseModel):
    """Qué quiere el dueño que haga el asistente con este mensaje."""

    intention: Literal["send_message", "quote", "invoice", "confirm", "chat"] = "chat"
    contact_name: str | None = Field(default=None, max_length=100)
    message_text: str | None = Field(default=None, max_length=1000)
    # Para invoice: monto y concepto
    amount: float | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=500)
