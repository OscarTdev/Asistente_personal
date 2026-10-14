"""pg_trgm: similitud del catalogo con umbral y indice GIN

Revision ID: 9a01a9fb73bd
Revises: 48d23d9bcf0f
Create Date: 2026-10-14 02:49:09.393159

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a01a9fb73bd'
down_revision: Union[str, None] = '48d23d9bcf0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Similitud de texto para el matching del catálogo (spec B4+).
    # pg_trgm viene incluido en la imagen pgvector/pgvector (Postgres contrib).
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "ix_catalog_items_name_trgm",
        "catalog_items",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_items_name_trgm", table_name="catalog_items")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
