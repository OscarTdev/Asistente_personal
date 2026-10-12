from abc import ABC, abstractmethod
from typing import Any

from app.schemas.channel import IncomingMessage


class ChannelParseError(Exception):
    """Error al parsear el payload del canal."""
    pass


class SelfMessageIgnored(ChannelParseError):
    """Mensaje enviado desde el propio número del bot: se acusa recibo y se ignora."""
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

    async def send_document(
        self, to: str, file_name: str, content_base64: str, mimetype: str
    ) -> None:
        """Envía un documento (ej: PDF de cotización). Las subclases lo implementan."""
        raise NotImplementedError(f"{self.name} no soporta envío de documentos")