"""Seed no interactivo: crea un tenant y su usuario admin.

Uso (desde backend/, con el venv activo):
    python -m scripts.create_admin --email admin@example.com
    python -m scripts.create_admin --tenant-name "Personal" --email admin@example.com
    python -m scripts.create_admin --email admin@example.com --password Secreta123

Comportamiento:
- Tenant: se crea si el slug no existe; si existe, se reutiliza.
- Usuario: si (tenant, email) ya existe → SystemExit(1).
"""

import argparse
import asyncio
import getpass
import re
import sys
import unicodedata
import uuid

# psycopg async cannot run on Windows' default ProactorEventLoop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import SessionFactory
from app.core.security import hash_password
from app.models import Tenant, User


def slugify(value: str) -> str:
    """Normaliza un nombre a slug: sin acentes, minúsculas, [a-z0-9-], sin bordes de guion."""
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


async def run(
    tenant_name: str,
    bot_name: str,
    slug: str,
    email: str,
    password: str,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict:
    """Crea (o reutiliza) el tenant y crea el admin. Devuelve ids como dict."""
    factory = session_factory or SessionFactory
    async with factory() as session:
        result = await session.execute(select(Tenant).where(Tenant.slug == slug))
        tenant = result.scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(
                id=uuid.uuid4(), name=tenant_name, slug=slug, bot_name=bot_name
            )
            session.add(tenant)
            try:
                await session.flush()
            except IntegrityError:
                # Carrera: otro proceso creó el slug entre el select y el insert.
                await session.rollback()
                result = await session.execute(select(Tenant).where(Tenant.slug == slug))
                tenant = result.scalar_one_or_none()
                if tenant is None:
                    raise

        result = await session.execute(
            select(User).where(User.tenant_id == tenant.id, User.email == email)
        )
        if result.scalar_one_or_none() is not None:
            print(
                f"El usuario {email} ya existe en el tenant '{slug}'.",
                file=sys.stderr,
            )
            raise SystemExit(1)

        user = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email=email,
            password_hash=hash_password(password),
            full_name=None,
            role="admin",
            is_active=True,
        )
        session.add(user)
        await session.commit()

        await session.refresh(tenant)
        await session.refresh(user)
        return {
            "tenant_id": tenant.id,
            "tenant_slug": tenant.slug,
            "user_id": user.id,
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crea un tenant y su usuario admin (seed no interactivo)."
    )
    parser.add_argument("--tenant-name", default="Personal", help="Nombre del tenant")
    parser.add_argument("--bot-name", default="Aura", help="Nombre del bot del tenant")
    parser.add_argument(
        "--slug",
        default=None,
        help="Slug del tenant (por defecto: slugify del nombre)",
    )
    parser.add_argument("--email", required=True, help="Email del admin")
    parser.add_argument(
        "--password",
        default=None,
        help="Contraseña (si se omite, se pide por getpass)",
    )
    args = parser.parse_args()

    slug = args.slug or slugify(args.tenant_name)
    password = args.password
    if password is None:
        password = getpass.getpass(f"Contraseña para {args.email}: ")
    if not password:
        print("La contraseña no puede estar vacía.", file=sys.stderr)
        raise SystemExit(1)

    result = asyncio.run(
        run(
            tenant_name=args.tenant_name,
            bot_name=args.bot_name,
            slug=slug,
            email=args.email,
            password=password,
        )
    )
    print(f"Tenant: {result['tenant_slug']} ({result['tenant_id']})")
    print(f"Admin:  {result['user_id']}")


if __name__ == "__main__":
    main()
