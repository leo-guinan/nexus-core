"""add documents table

Revision ID: 20240401_add_documents_table
Revises: 20240321_add_sponsor_model
Create Date: 2024-04-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20240401_add_documents_table'
down_revision = '20240321_add_sponsor_model'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'documents',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('file_type', sa.String(), nullable=False),
        sa.Column('gcs_path', sa.String(), nullable=False),
        sa.Column('fulltext_content', sa.Text(), nullable=True),
        sa.Column('chroma_status', sa.String(), nullable=False),
        sa.Column('chunks_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_chunks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('ix_documents_user_id', 'user_id'),
        sa.Index('ix_documents_created_at', 'created_at')
    )


def downgrade() -> None:
    op.drop_table('documents') 