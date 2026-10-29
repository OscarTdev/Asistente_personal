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
    # Canal lógico para las identidades (channel_identities): "whatsapp",
    # "telegram", "web"... — independiente de la implementación (evolution).
    identity_channel: str = "whatsapp"

    @abstractmethod
    async def parse_incoming(self, payload: dict[str, Any]) -> IncomingMessage:
        """Convierte el payload del canal en un IncomingMessage.

        NO descarta los mensajes fromMe aquí: la ingesta decide (el auto-chat
        del dueño es una conversación válida con el asistente).
        """
        pass

    @abstractmethod
    async def send_text(self, to: str, text: str) -> str | None:
        """Envía un mensaje de texto vía el canal.

        Devuelve el id del mensaje creado si el canal lo entrega: se usa
        para deduplicar el eco de nuestros propios envíos en el webhook.
        """
        pass

    async def send_document(
        self, to: str, file_name: str, content_base64: str, mimetype: str
    ) -> str | None:
        """Envía un documento (ej: PDF de cotización). Devuelve el id del mensaje."""
        raise NotImplementedError(f"{self.name} no soporta envío de documentos")

    async def mark_read(self, to: str, message_id: str) -> None:
        """Marca un mensaje entrante como leído (check azul).

        Anti-detección: un bot que responde al instante sin leer jamás es
        patrón de automatización para Meta. No-op por defecto.
        """
        return None

    async def send_typing(self, to: str, *, composing: bool = True) -> None:
        """Muestra/oculta el indicador «escribiendo…» en el chat.

        composing=True al empezar a procesar, False tras responder.
        No-op por defecto.
        """
        return None

    async def send_buttons(
        self, to: str, text: str, buttons: list[dict[str, str]], footer: str | None = None
    ) -> str | None:
        """Envía mensaje con botones de respuesta (reply buttons).
        
        buttons: lista de dicts con keys 'id' y 'title'.
        footer: texto opcional al pie.
        """
        raise NotImplementedError(f"{self.name} no soporta botones")

    async def send_list(
        self, to: str, text: str, button_text: str, sections: list[dict], title: str | None = None
    ) -> str | None:
        """Envía mensaje con lista (list message).
        
        sections: lista de dicts con 'title' y 'rows' (cada row con 'id', 'title', 'description').
        button_text: texto del botón que abre la lista.
        title: título opcional de la lista.
        """
        raise NotImplementedError(f"{self.name} no soporta listas")

    async def send_poll(
        self, to: str, question: str, options: list[str]
    ) -> str | None:
        """Envía una encuesta (poll).
        
        options: lista de opciones (máx 12, min 2).
        """
        raise NotImplementedError(f"{self.name} no soporta encuestas")