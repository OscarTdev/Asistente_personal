"""Tests del seed script (Task 13 del plan)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.security import verify_password
from app.models import Tenant, User
from scripts.create_admin import run, slugify


def factory_for(test_engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_run_creates_tenant_and_admin(test_engine, db_session):
    """Primera corrida: crea tenant "personal" + admin con password verificable."""
    factory = factory_for(test_engine)
    result = await run(
        tenant_name="Personal",
        bot_name="Aura",
        slug="personal",
        email="admin@example.com",
        password="Admin1234!",
        session_factory=factory,
    )

    assert result["tenant_slug"] == "personal"

    async with factory() as session:
        user = (
            await session.execute(select(User).where(User.id == result["user_id"]))
        ).scalar_one()
        tenant = (
            await session.execute(select(Tenant).where(Tenant.id == result["tenant_id"]))
        ).scalar_one()

    assert verify_password("Admin1234!", user.password_hash) is True
    assert user.role == "admin"
    assert user.is_active is True
    assert tenant.bot_name == "Aura"


@pytest.mark.asyncio
async def test_run_reuses_existing_tenant(test_engine, db_session):
    """Segunda corrida con otro email: reutiliza el tenant, no crea otro."""
    factory = factory_for(test_engine)
    first = await run(
        tenant_name="Personal",
        bot_name="Aura",
        slug="personal",
        email="admin@example.com",
        password="Admin1234!",
        session_factory=factory,
    )
    second = await run(
        tenant_name="Personal",
        bot_name="Aura",
        slug="personal",
        email="other@example.com",
        password="Other1234!",
        session_factory=factory,
    )

    assert second["tenant_id"] == first["tenant_id"]

    async with factory() as session:
        tenants = (
            await session.execute(select(Tenant).where(Tenant.slug == "personal"))
        ).scalars().all()
        assert len(tenants) == 1


@pytest.mark.asyncio
async def test_run_rejects_duplicate_email(test_engine, db_session):
    """Segunda corrida con el mismo (tenant, email) → SystemExit."""
    factory = factory_for(test_engine)
    await run(
        tenant_name="Personal",
        bot_name="Aura",
        slug="personal",
        email="admin@example.com",
        password="Admin1234!",
        session_factory=factory,
    )

    with pytest.raises(SystemExit):
        await run(
            tenant_name="Personal",
            bot_name="Aura",
            slug="personal",
            email="admin@example.com",
            password="Other1234!",
            session_factory=factory,
        )


def test_slugify():
    """slugify normaliza a [a-z0-9-] sin bordes de guion."""
    assert slugify("Personal") == "personal"
    assert slugify("Mi Tienda & Co") == "mi-tienda-co"
    assert slugify("  Taller--Doña  Rosa  ") == "taller-dona-rosa"
