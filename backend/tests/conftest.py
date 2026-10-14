"""Shared pytest fixtures.

Windows: psycopg async cannot use the default ProactorEventLoop, so switch to
the selector policy before anything creates an engine. Tests run against a
dedicated `asistente_test` database, recreated on every session; each test
starts from truncated tables.
"""

import asyncio
import sys
import uuid

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.channels.evolution import EvolutionChannel
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Base, Tenant, User

TEST_DB_NAME = "asistente_test"


@pytest.fixture(scope="session")
async def test_engine() -> AsyncIterator[AsyncEngine]:
    """Recreate `asistente_test` from scratch and create the schema."""
    settings = get_settings()
    # URL object (not str): str(URL) masks the password as "***"
    admin_url = make_url(settings.database_url).set(database="postgres")
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        await conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"')
        await conn.exec_driver_sql(f'CREATE DATABASE "{TEST_DB_NAME}"')
    await admin_engine.dispose()

    engine = create_async_engine(
        make_url(settings.database_url).set(database=TEST_DB_NAME),
        pool_pre_ping=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Empty tables per test: TRUNCATE everything, then yield a plain session."""
    async with test_engine.begin() as conn:
        table_list = ", ".join(
            f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables)
        )
        await conn.execute(text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"))
    session = async_sessionmaker(test_engine, expire_on_commit=False)()
    yield session
    await session.close()


class _StubChannel(EvolutionChannel):
    """EvolutionChannel que parsea real pero NUNCA envía.

    El webhook dispara el orquestador en background; sin esto, un
    prospecto en un test haría un envío real de WhatsApp. El parseo sí
    es el de verdad: la ingesta y sus tests dependen de él.
    """

    name = "stub"

    async def send_text(self, to: str, text: str) -> str | None:
        return None

    async def send_document(
        self, to: str, file_name: str, content_base64: str, mimetype: str
    ) -> str | None:
        return None

    async def connection_state(self) -> dict:
        return {"instance": {"state": "offline"}}

    async def connect_qr(self) -> dict:
        return {"instance": {"state": "offline"}}


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Test client whose get_db dependency uses the test session."""

    async def override_get_db():
        yield db_session

    from app.api.v1 import webhooks as webhooks_module

    original_get_channel = webhooks_module.get_channel
    webhooks_module.get_channel = lambda name="evolution": _StubChannel()

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
    webhooks_module.get_channel = original_get_channel


@pytest.fixture
async def tenant(db_session: AsyncSession) -> Tenant:
    """Test tenant: name="Personal", slug="personal", bot_name="Aura"."""
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Personal",
        slug="personal",
        bot_name="Aura",
        is_active=True,
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest.fixture
async def admin_user(db_session: AsyncSession, tenant: Tenant) -> User:
    """Test admin: email="admin@example.com", password "Admin1234!"."""
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="admin@example.com",
        password_hash=hash_password("Admin1234!"),
        full_name=None,
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def webhook_headers(monkeypatch) -> dict[str, str]:
    """Secreto del webhook para los tests (y el settings parchado que lo valida).

    El webhook de WhatsApp es fail-closed: sin cabecera X-Webhook-Secret
    correcta responde 401. Este fixture parchea los settings del dep y
    devuelve la cabecera válida.
    """
    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.api.deps.get_settings",
        lambda: SimpleNamespace(
            webhook_secret="test-webhook-secret",
            platform_tenant_slug="plataforma",
        ),
    )
    return {"X-Webhook-Secret": "test-webhook-secret"}
