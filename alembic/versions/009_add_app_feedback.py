"""Add app_feedback table

Revision ID: 009
Revises: 008
Create Date: 2026-01-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create app_feedback table."""
    op.create_table(
        'app_feedback',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('page_url', sa.String(), nullable=True),
        sa.Column('is_resolved', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_app_feedback_user_id', 'app_feedback', ['user_id'])
    op.create_index('ix_app_feedback_is_resolved', 'app_feedback', ['is_resolved'])
    op.create_index('ix_app_feedback_created_at', 'app_feedback', ['created_at'])


def downgrade() -> None:
    """Drop app_feedback table."""
    op.drop_index('ix_app_feedback_created_at', table_name='app_feedback')
    op.drop_index('ix_app_feedback_is_resolved', table_name='app_feedback')
    op.drop_index('ix_app_feedback_user_id', table_name='app_feedback')
    op.drop_table('app_feedback')
