"""Esquemas del asistente del dueño (router de intenciones)."""

from typing import Literal

from pydantic import BaseModel, Field


class AssistantIntent(BaseModel):
    """Qué quiere el dueño que haga el asistente con este mensaje."""

    intention: Literal["send_message", "quote", "chat"] = "chat"
    contact_name: str | None = Field(default=None, max_length=100)
    message_text: str | None = Field(default=None, max_length=1000)
