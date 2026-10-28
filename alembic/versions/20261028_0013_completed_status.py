"""Protect completed statuses for every writer, including bulk SQL updates."""

from alembic import op

revision = '20261028_0013'
down_revision = '20261028_0012'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_chat_login_tokens_expires_at', 'chat_login_tokens', ['expires_at'])
    op.create_index('ix_password_reset_tokens_expires_at', 'password_reset_tokens', ['expires_at'])
    op.execute("""
        CREATE FUNCTION kyrgyzgo_guard_completed_request() RETURNS trigger AS $$
        BEGIN
            IF OLD.status::text = 'completed' AND NEW.status IS DISTINCT FROM OLD.status THEN
                RAISE EXCEPTION 'Completed requests cannot change status' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER kyrgyzgo_completed_request
        BEFORE UPDATE OF status ON travel_requests
        FOR EACH ROW EXECUTE FUNCTION kyrgyzgo_guard_completed_request();
    """)


def downgrade():
    op.execute('DROP TRIGGER kyrgyzgo_completed_request ON travel_requests')
    op.execute('DROP FUNCTION kyrgyzgo_guard_completed_request()')
    op.drop_index('ix_password_reset_tokens_expires_at', table_name='password_reset_tokens')
    op.drop_index('ix_chat_login_tokens_expires_at', table_name='chat_login_tokens')
