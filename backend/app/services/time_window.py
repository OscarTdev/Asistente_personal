"""Hora Colombia (UTC-5, sin horario de verano): fuente única de verdad.

Todo el proyecto calcula la hora local con esta regla — el país no
cambia de reloj. Antes había dos copias del cálculo del "mes actual"
(expenses y google_actions) que se desincronizaban; ahora viven aquí.
"""

from datetime import UTC, datetime, timedelta


def to_colombia(dt: datetime) -> datetime:
    """Un datetime UTC → su hora Colombia equivalente (UTC-5)."""
    return dt - timedelta(hours=5)


def colombia_now() -> datetime:
    """La hora actual en términos de Colombia (UTC-5)."""
    return to_colombia(datetime.now(UTC))


def month_bounds(now_col: datetime) -> tuple[datetime, datetime]:
    """Ventana [inicio, fin) del mes LOCAL que contiene now_col, en UTC.

    Recibe la hora Colombia y devuelve los límites del mes colombiano
    convertidos a UTC para las consultas SQL.
    """
    start_col = now_col.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start_col.month == 12:
        end_col = start_col.replace(year=start_col.year + 1, month=1)
    else:
        end_col = start_col.replace(month=start_col.month + 1)
    return start_col + timedelta(hours=5), end_col + timedelta(hours=5)
