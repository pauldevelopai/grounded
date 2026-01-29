"""Add tool reviews, votes, and flags tables

Revision ID: 012
Revises: 011
Create Date: 2025-01-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade():
    # Create tool_reviews table
    op.create_table(
        'tool_reviews',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tool_slug', sa.String(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('use_case_tag', sa.String(), nullable=True),
        sa.Column('is_hidden', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('hidden_reason', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'tool_slug', name='uq_user_tool_review'),
        sa.CheckConstraint('rating >= 1 AND rating <= 5', name='ck_rating_range'),
    )
    op.create_index('ix_tool_reviews_user_id', 'tool_reviews', ['user_id'])
    op.create_index('ix_tool_reviews_tool_slug', 'tool_reviews', ['tool_slug'])
    op.create_index('ix_tool_reviews_created_at', 'tool_reviews', ['created_at'])

    # Create review_votes table
    op.create_table(
        'review_votes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('review_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('is_helpful', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['review_id'], ['tool_reviews.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('review_id', 'user_id', name='uq_review_user_vote'),
    )
    op.create_index('ix_review_votes_review_id', 'review_votes', ['review_id'])
    op.create_index('ix_review_votes_user_id', 'review_votes', ['user_id'])

    # Create review_flags table
    op.create_table(
        'review_flags',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('review_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('resolved_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['review_id'], ['tool_reviews.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('review_id', 'user_id', name='uq_review_user_flag'),
    )
    op.create_index('ix_review_flags_review_id', 'review_flags', ['review_id'])
    op.create_index('ix_review_flags_user_id', 'review_flags', ['user_id'])
    op.create_index('ix_review_flags_is_resolved', 'review_flags', ['is_resolved'])


def downgrade():
    op.drop_table('review_flags')
    op.drop_table('review_votes')
    op.drop_table('tool_reviews')
