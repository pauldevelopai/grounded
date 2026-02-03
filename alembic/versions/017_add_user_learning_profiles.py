"""Add user_learning_profiles table for personalized recommendations.

Revision ID: 017_add_user_learning_profiles
Revises: 016_add_tool_suggestions
Create Date: 2025-02-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_learning_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('preferred_clusters', postgresql.JSONB(), nullable=True, server_default='{}'),
        sa.Column('tool_interests', postgresql.JSONB(), nullable=True, server_default='{}'),
        sa.Column('searched_topics', postgresql.JSONB(), nullable=True, server_default='[]'),
        sa.Column('strategy_feedback', postgresql.JSONB(), nullable=True, server_default='[]'),
        sa.Column('dismissed_tools', postgresql.JSONB(), nullable=True, server_default='[]'),
        sa.Column('favorited_tools', postgresql.JSONB(), nullable=True, server_default='[]'),
        sa.Column('profile_summary', sa.Text(), nullable=True),
        sa.Column('last_summary_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_activity_count', postgresql.JSONB(), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', name='uq_user_learning_profile_user_id'),
    )

    # Create index on user_id for fast lookups
    op.create_index('ix_user_learning_profiles_user_id', 'user_learning_profiles', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_user_learning_profiles_user_id', table_name='user_learning_profiles')
    op.drop_table('user_learning_profiles')
