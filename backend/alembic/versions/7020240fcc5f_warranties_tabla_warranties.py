"""warranties: tabla warranties

Revision ID: 7020240fcc5f
Revises: 7f3eab67cb2b
Create Date: 2026-10-16 15:28:16.830026

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7020240fcc5f'
down_revision: Union[str, None] = '7f3eab67cb2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('warranties',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('contact_id', sa.UUID(), nullable=False),
    sa.Column('item', sa.Text(), nullable=False),
    sa.Column('installed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], name=op.f('fk_warranties_contact_id_contacts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_warranties_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_warranties'))
    )
    op.create_index(op.f('ix_warranties_expires_at'), 'warranties', ['expires_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_warranties_expires_at'), table_name='warranties')
    op.drop_table('warranties')
