"""Schemas del dashboard del panel: métricas del asistente."""

from pydantic import BaseModel


class ContactsStats(BaseModel):
    total: int
    active_last_7d: int


class QuotesStats(BaseModel):
    total: int
    last_7d: int
    by_status: dict[str, int]


class ServiceStat(BaseModel):
    key: str
    name: str
    dev_status: str
    is_enabled: bool
    interactions: int
    interactions_7d: int


class DashboardStats(BaseModel):
    bot_name: str
    contacts: ContactsStats
    quotes: QuotesStats
    services: list[ServiceStat]
    messages_last_7d: int
