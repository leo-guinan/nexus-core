"""Add entity recognition table

Revision ID: d790e3e4afbb
Revises: 
Create Date: 2024-03-19 12:34:56.789012

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd790e3e4afbb'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('entity_recognition',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stream_id', sa.String(), nullable=True),
        sa.Column('entities', sa.JSON(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_entity_recognition_id'), 'entity_recognition', ['id'], unique=False)
    op.create_index(op.f('ix_entity_recognition_stream_id'), 'entity_recognition', ['stream_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_entity_recognition_stream_id'), table_name='entity_recognition')
    op.drop_index(op.f('ix_entity_recognition_id'), table_name='entity_recognition')
    op.drop_table('entity_recognition')
