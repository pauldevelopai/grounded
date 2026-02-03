"""Add tool_suggestions table for user tool submissions.

Revision ID: 016_add_tool_suggestions
Revises: 015_add_suggested_sources
Create Date: 2025-02-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'tool_suggestions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(500), nullable=False),
        sa.Column('url', sa.String(2000), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('why_valuable', sa.Text(), nullable=True),
        sa.Column('use_cases', sa.Text(), nullable=True),
        sa.Column('submitted_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('reviewed_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_notes', sa.Text(), nullable=True),
        sa.Column('converted_tool_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['submitted_by'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['converted_tool_id'], ['discovered_tools.id'], ondelete='SET NULL'),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'converted')", name='ck_tool_suggestion_status'),
    )

    # Create indexes
    op.create_index('ix_tool_suggestions_submitted_by', 'tool_suggestions', ['submitted_by'])
    op.create_index('ix_tool_suggestions_submitted_at', 'tool_suggestions', ['submitted_at'])
    op.create_index('ix_tool_suggestions_status', 'tool_suggestions', ['status'])
    op.create_index('ix_tool_suggestions_reviewed_by', 'tool_suggestions', ['reviewed_by'])


def downgrade() -> None:
    op.drop_index('ix_tool_suggestions_reviewed_by', table_name='tool_suggestions')
    op.drop_index('ix_tool_suggestions_status', table_name='tool_suggestions')
    op.drop_index('ix_tool_suggestions_submitted_at', table_name='tool_suggestions')
    op.drop_index('ix_tool_suggestions_submitted_by', table_name='tool_suggestions')
    op.drop_table('tool_suggestions')
