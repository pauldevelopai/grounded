"""initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
# from pgvector.sqlalchemy import Vector  # Temporarily disabled

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    # op.execute('CREATE EXTENSION IF NOT EXISTS vector')  # Temporarily disabled

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # Create toolkit_documents table
    op.create_table(
        'toolkit_documents',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('version_tag', sa.String(), nullable=False),
        sa.Column('source_filename', sa.String(), nullable=False),
        sa.Column('uploaded_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('upload_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('chunk_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
    )
    op.create_index('ix_toolkit_documents_version_tag', 'toolkit_documents', ['version_tag'], unique=True)

    # Create toolkit_chunks table
    op.create_table(
        'toolkit_chunks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('toolkit_documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('cluster', sa.String(), nullable=True),
        sa.Column('section', sa.String(), nullable=True),
        sa.Column('tool_name', sa.String(), nullable=True),
        sa.Column('tags', JSONB, nullable=True),
        # sa.Column('embedding', Vector(1536), nullable=True),  # Temporarily disabled - requires pgvector
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_toolkit_chunks_document_id', 'toolkit_chunks', ['document_id'])

    # Create chat_logs table
    op.create_table(
        'chat_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('citations', JSONB, nullable=False),
        sa.Column('retrieval_confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_chat_logs_user_id', 'chat_logs', ['user_id'])

    # Create feedback table
    op.create_table(
        'feedback',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chat_log_id', UUID(as_uuid=True), sa.ForeignKey('chat_logs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('issue_type', sa.String(), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_feedback_user_id', 'feedback', ['user_id'])
    op.create_index('ix_feedback_chat_log_id', 'feedback', ['chat_log_id'])

    # Create strategy_plans table
    op.create_table(
        'strategy_plans',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('inputs', JSONB, nullable=False),
        sa.Column('outputs', JSONB, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_strategy_plans_user_id', 'strategy_plans', ['user_id'])


def downgrade() -> None:
    op.drop_table('strategy_plans')
    op.drop_table('feedback')
    op.drop_table('chat_logs')
    op.drop_table('toolkit_chunks')
    op.drop_table('toolkit_documents')
    op.drop_table('users')
    # op.execute('DROP EXTENSION IF EXISTS vector')  # Temporarily disabled
