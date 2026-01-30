"""Add suggested_sources table for user source submissions.

Revision ID: 015_add_suggested_sources
Revises: 014_add_tool_playbooks
Create Date: 2025-01-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'suggested_sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('submitted_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('url', sa.String(2000), nullable=False),
        sa.Column('source_type', sa.String(50), nullable=False, server_default='article'),
        sa.Column('excerpt', sa.Text(), nullable=True),
        sa.Column('why_valuable', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('reviewed_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_notes', sa.Text(), nullable=True),
        sa.Column('added_to_batch', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['submitted_by'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='SET NULL'),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name='ck_suggested_source_status'),
        sa.CheckConstraint("source_type IN ('article', 'report', 'study', 'guide', 'other')", name='ck_suggested_source_type'),
    )

    # Create indexes
    op.create_index('ix_suggested_sources_submitted_by', 'suggested_sources', ['submitted_by'])
    op.create_index('ix_suggested_sources_status', 'suggested_sources', ['status'])
    op.create_index('ix_suggested_sources_created_at', 'suggested_sources', ['created_at'])
    op.create_index('ix_suggested_sources_reviewed_by', 'suggested_sources', ['reviewed_by'])


def downgrade() -> None:
    op.drop_index('ix_suggested_sources_reviewed_by', table_name='suggested_sources')
    op.drop_index('ix_suggested_sources_created_at', table_name='suggested_sources')
    op.drop_index('ix_suggested_sources_status', table_name='suggested_sources')
    op.drop_index('ix_suggested_sources_submitted_by', table_name='suggested_sources')
    op.drop_table('suggested_sources')
