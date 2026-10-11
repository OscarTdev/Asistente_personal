"""Test that the fixtures work correctly."""

import uuid

import pytest
from sqlalchemy import select

from app.models import Tenant


@pytest.mark.asyncio
async def test_tenant_creation(tenant):
    """Test that a tenant is created correctly."""
    assert tenant.id is not None
    assert tenant.name == "Personal"
    assert tenant.slug == "personal"
    assert tenant.bot_name == "Aura"
    assert tenant.is_active is True


@pytest.mark.asyncio
async def test_admin_user_creation(admin_user, tenant):
    """Test that an admin user is created correctly."""
    assert admin_user.id is not None
    assert admin_user.email == "admin@example.com"
    assert admin_user.tenant_id == tenant.id
    assert admin_user.role == "admin"
    assert admin_user.is_active is True


@pytest.mark.asyncio
async def test_database_isolation(db_session):
    """Test that each test gets a clean database."""
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Test",
        slug="test",
        bot_name="TestBot",
        is_active=True,
    )
    db_session.add(tenant)
    await db_session.commit()

    result = await db_session.execute(select(Tenant))
    tenants = result.scalars().all()
    assert len(tenants) == 1
    assert tenants[0].name == "Test"

    # TRUNCATE per test: the next test starts from empty tables
