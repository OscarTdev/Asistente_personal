"""Precio de los planes configurable desde el panel de administración.

Tabla de plataforma (sin tenant_id, como tenants): el precio de un plan es
un parámetro del negocio, no de cada inquilino. Sin fila → el precio vigente
es el default del código (modules_registry.PLAN_PRICE_COP).
"""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PlanPrice(Base, TimestampMixin):
    __tablename__ = "plan_prices"

    plan: Mapped[str] = mapped_column(String(20), primary_key=True)
    price_cop: Mapped[int] = mapped_column(Integer, nullable=False)
