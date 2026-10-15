"""Entitlements por plan configurados desde el panel Admin (super admin).

Qué servicio incluye cada plan (Prueba/Freemium/Premium) — la matriz
"gratis vs VIP". Sin filas → el default del código (modules_registry).
"""

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PlanEntitlement(Base, TimestampMixin):
    __tablename__ = "plan_entitlements"
    __table_args__ = (
        UniqueConstraint("plan", "module_key", name="uq_plan_entitlements"),
    )

    plan: Mapped[str] = mapped_column(String(20), primary_key=True)
    module_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
