"""Tests del matching de catálogo: similitud pg_trgm, comodines y ambigüedad.

El matching usa pg_trgm con umbral (tolera «30 A» vs «30A»), respaldo
ILIKE escapado para términos cortos, y NO matchea cuando dos ítems
empatan: mejor confirmar que enviar el precio equivocado.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, Tenant
from app.services.ai_extraction import _match_catalog_item


async def _seed_catalog(db_session: AsyncSession, tenant, *names: str) -> None:
    for name in names:
        db_session.add(
            CatalogItem(
                tenant_id=tenant.id,
                name=name,
                description=None,
                unit="unidad",
                unit_price=1000,
                is_active=True,
            )
        )
    await db_session.commit()


async def test_wildcards_do_not_match_everything(
    db_session: AsyncSession, tenant: Tenant
):
    """%, _, \\ en el texto de la IA no pueden robar el precio de otro ítem."""
    await _seed_catalog(db_session, tenant, "Breaker bipolar 30A")

    for poison in ("%", "_", "\\", "%A%"):
        match = await _match_catalog_item(
            db_session, tenant_id=tenant.id, description=poison
        )
        assert match is None, f"El comodín {poison!r} matcheó el catálogo"


async def test_exact_description_matches(
    db_session: AsyncSession, tenant: Tenant
):
    """El matching normal no se rompe: el nombre exacto matchea."""
    await _seed_catalog(db_session, tenant, "Breaker bipolar 30A")

    match = await _match_catalog_item(
        db_session, tenant_id=tenant.id, description="Breaker bipolar 30A"
    )
    assert match is not None
    assert match.name == "Breaker bipolar 30A"


async def test_similarity_tolerates_variants(
    db_session: AsyncSession, tenant: Tenant
):
    """«Breaker bipolar 30 A» (con espacio) matchea «Breaker bipolar 30A»."""
    await _seed_catalog(db_session, tenant, "Breaker bipolar 30A")

    match = await _match_catalog_item(
        db_session, tenant_id=tenant.id, description="Breaker bipolar 30 A"
    )
    assert match is not None
    assert match.name == "Breaker bipolar 30A"


async def test_short_term_falls_back_to_ilike(
    db_session: AsyncSession, tenant: Tenant
):
    """«breaker» es corto para trigramas: el respaldo ILIKE lo encuentra."""
    await _seed_catalog(db_session, tenant, "Breaker bipolar 30A")

    match = await _match_catalog_item(
        db_session, tenant_id=tenant.id, description="breaker"
    )
    assert match is not None
    assert match.name == "Breaker bipolar 30A"


async def test_unknown_description_returns_none(
    db_session: AsyncSession, tenant: Tenant
):
    await _seed_catalog(db_session, tenant, "Breaker bipolar 30A")

    match = await _match_catalog_item(
        db_session, tenant_id=tenant.id, description="Tablero de control industrial"
    )
    assert match is None


async def test_ambiguous_match_returns_none(
    db_session: AsyncSession, tenant: Tenant
):
    """Dos ítems casi idénticos: no se elige — mejor confirmar."""
    await _seed_catalog(db_session, tenant, "Cable THHN #12", "Cable THHN #14")

    # «Cable THHN» empata con ambos: brecha < 0.05 → sin match
    match = await _match_catalog_item(
        db_session, tenant_id=tenant.id, description="Cable THHN"
    )
    assert match is None


async def test_tenant_isolation_in_matching(
    db_session: AsyncSession, tenant: Tenant
):
    """El catálogo de OTRO tenant nunca matchea: aislamiento."""
    other = Tenant(
        id=uuid.uuid4(),
        name="Otro Negocio",
        slug=f"otro-{uuid.uuid4().hex[:8]}",
        bot_name="Aura",
        is_active=True,
    )
    db_session.add(other)
    await db_session.flush()
    await _seed_catalog(db_session, other, "Tomacorriente doble")
    await db_session.commit()

    match = await _match_catalog_item(
        db_session, tenant_id=tenant.id, description="Tomacorriente doble"
    )
    assert match is None  # el catálogo del otro tenant no existe para este
