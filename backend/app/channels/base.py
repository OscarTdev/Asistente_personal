from abc import ABC, abstractmethod
from typing import Any

from app.schemas.channel import IncomingMessage


class ChannelParseError(Exception):
    """Error al parsear el payload del canal."""
    pass


class Channel(ABC):
    name: str  # se sobrescribe en la subclase

    @abstractmethod
    async def parse_incoming(self, payload: dict[str, Any]) -> IncomingMessage:
        """Convierte el payload del canal en un IncomingMessage."""
        pass

    @abstractmethod
    async def send_text(self, to: str, text: str) -> None:
        """Envía un mensaje de texto vía el canal."""
        pass