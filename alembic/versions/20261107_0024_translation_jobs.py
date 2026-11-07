"""Persist translation work and retry state across process restarts."""

import sqlalchemy as sa

from alembic import op

revision = '20261107_0024'
down_revision = '20261107_0023'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'translation_jobs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('entity', sa.String(length=80), nullable=False),
        sa.Column('record_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column(
            'next_attempt_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.String(length=80), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('entity', 'record_id', name='uq_translation_job_target'),
    )
    op.create_index(
        'ix_translation_jobs_status_due', 'translation_jobs', ['status', 'next_attempt_at']
    )


def downgrade():
    op.drop_index('ix_translation_jobs_status_due', table_name='translation_jobs')
    op.drop_table('translation_jobs')
