from pydantic import BaseModel


class WebhookAck(BaseModel):
    status: str = "ok"
    whatsapp_message_id: str
    duplicate: bool = False
