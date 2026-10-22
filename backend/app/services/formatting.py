"""Formato de dinero en pantalla: COP con puntos de miles ($1.250.000)."""

from decimal import Decimal


def format_cop(amount: Decimal | float | int) -> str:
    """Formatea un monto en pesos colombianos; nunca revienta."""
    try:
        return f"${float(amount):,.0f}".replace(",", ".")
    except Exception:
        return f"${amount}"
