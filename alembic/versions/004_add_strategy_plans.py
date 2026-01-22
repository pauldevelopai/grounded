"""Add strategy_plans table

Revision ID: 004
Revises: 003
Create Date: 2025-01-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create strategy_plans table."""
    op.create_table(
        'strategy_plans',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('inputs', JSONB, nullable=False),
        sa.Column('plan_text', sa.Text(), nullable=False),
        sa.Column('citations', JSONB, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_strategy_plans_user_id', 'strategy_plans', ['user_id'])
    op.create_index('ix_strategy_plans_created_at', 'strategy_plans', ['created_at'])


def downgrade() -> None:
    """Drop strategy_plans table."""
    op.drop_index('ix_strategy_plans_created_at', table_name='strategy_plans')
    op.drop_index('ix_strategy_plans_user_id', table_name='strategy_plans')
    op.drop_table('strategy_plans')
