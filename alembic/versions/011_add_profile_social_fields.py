"""Add bio and social media fields to users

Revision ID: 011
Revises: 010
Create Date: 2025-01-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('bio', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('website', sa.String(), nullable=True))
    op.add_column('users', sa.Column('twitter', sa.String(), nullable=True))
    op.add_column('users', sa.Column('linkedin', sa.String(), nullable=True))
    op.add_column('users', sa.Column('organisation_website', sa.String(), nullable=True))
    op.add_column('users', sa.Column('organisation_notes', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('users', 'organisation_notes')
    op.drop_column('users', 'organisation_website')
    op.drop_column('users', 'linkedin')
    op.drop_column('users', 'twitter')
    op.drop_column('users', 'website')
    op.drop_column('users', 'bio')
