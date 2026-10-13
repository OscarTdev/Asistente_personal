"""Tests del matching de catálogo: comodines escapados (M1).

Antes: '%' o '_' en la descripción de la IA hacían ILIKE '%%%%' y casaban
con el primer ítem del catálogo, robando su precio.
"""


from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem
from app.services.ai_extraction import _match_catalog_item


async def _seed_catalog(db_session: AsyncSession, tenant) -> None:
    db_session.add(
        CatalogItem(
            tenant_id=tenant.id,
            name="Breaker bipolar 30A",
            description="Interruptor termomagnético bipolar",
            unit="unidad",
            unit_price=45000,
            is_active=True,
        )
    )
    await db_session.commit()


async def test_wildcards_do_not_match_everything(
    db_session: AsyncSession, tenant
):
    """%, _, \\ en el texto de la IA no pueden robar el precio de otro ítem."""
    await _seed_catalog(db_session, tenant)

    for poison in ("%", "_", "\\", "%A%"):
        match = await _match_catalog_item(
            db_session, tenant_id=tenant.id, description=poison
        )
        assert match is None, f"El comodín {poison!r} matcheó el catálogo"


async def test_real_description_still_matches(
    db_session: AsyncSession, tenant
):
    """El matching normal no se rompe con el escape."""
    await _seed_catalog(db_session, tenant)

    match = await _match_catalog_item(
        db_session, tenant_id=tenant.id, description="Breaker bipolar 30A"
    )
    assert match is not None
    assert match.name == "Breaker bipolar 30A"


async def test_unknown_description_returns_none(
    db_session: AsyncSession, tenant
):
    await _seed_catalog(db_session, tenant)

    match = await _match_catalog_item(
        db_session, tenant_id=tenant.id, description="Tablero de control industrial"
    )
    assert match is None
