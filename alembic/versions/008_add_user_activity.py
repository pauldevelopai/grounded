"""Add user_activity table

Revision ID: 008
Revises: 007
Create Date: 2026-01-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create user_activity table."""
    op.create_table(
        'user_activity',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('activity_type', sa.String(), nullable=False),
        sa.Column('query', sa.Text(), nullable=True),
        sa.Column('details', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_user_activity_user_id', 'user_activity', ['user_id'])
    op.create_index('ix_user_activity_activity_type', 'user_activity', ['activity_type'])
    op.create_index('ix_user_activity_created_at', 'user_activity', ['created_at'])


def downgrade() -> None:
    """Drop user_activity table."""
    op.drop_index('ix_user_activity_created_at', table_name='user_activity')
    op.drop_index('ix_user_activity_activity_type', table_name='user_activity')
    op.drop_index('ix_user_activity_user_id', table_name='user_activity')
    op.drop_table('user_activity')
