"""Add PR #98 persistent session authentication tables (auth_users, auth_login_challenges, auth_sessions)."""
revision = '008_add_session_auth_tables'
down_revision = '007_add_family_tree_tables'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if 'auth_users' not in existing:
        op.create_table(
            'auth_users',
            sa.Column('user_id', sa.String(), primary_key=True),
            sa.Column('email', sa.String(), nullable=False, unique=True),
            sa.Column('display_name', sa.String(), nullable=False),
            sa.Column('scma_id', sa.String(), nullable=True),
            sa.Column('house_id', sa.String(), nullable=False, server_default='HOUSE-01'),
            sa.Column('authorized_hats', sa.Text(), nullable=False, server_default='["MEMBER_USER"]'),
            sa.Column('is_apex_tier3', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('passphrase_hash', sa.String(), nullable=True),
            sa.Column('mfa_secret_hash', sa.String(), nullable=True),
            sa.Column('active', sa.Integer(), nullable=False, server_default='1'),
        )
        op.create_index('ix_auth_users_email', 'auth_users', ['email'], unique=True)
        op.create_index('ix_auth_users_scma_id', 'auth_users', ['scma_id'])
        op.create_index('ix_auth_users_house_id', 'auth_users', ['house_id'])
        op.create_index('ix_auth_users_is_apex_tier3', 'auth_users', ['is_apex_tier3'])
        op.create_index('ix_auth_users_active', 'auth_users', ['active'])

    if 'auth_login_challenges' not in existing:
        op.create_table(
            'auth_login_challenges',
            sa.Column('challenge_id', sa.String(), primary_key=True),
            sa.Column('user_id', sa.String(), sa.ForeignKey('auth_users.user_id'), nullable=False),
            sa.Column('code_hash', sa.String(), nullable=False),
            sa.Column('magic_token_hash', sa.String(), nullable=False),
            sa.Column('expires_at', sa.String(), nullable=False),
            sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('consumed_at', sa.String(), nullable=True),
        )
        op.create_index('ix_auth_login_challenges_user_id', 'auth_login_challenges', ['user_id'])
        op.create_index('ix_auth_login_challenges_code_hash', 'auth_login_challenges', ['code_hash'])
        op.create_index('ix_auth_login_challenges_magic_token_hash', 'auth_login_challenges', ['magic_token_hash'])

    if 'auth_sessions' not in existing:
        op.create_table(
            'auth_sessions',
            sa.Column('session_id', sa.String(), primary_key=True),
            sa.Column('user_id', sa.String(), sa.ForeignKey('auth_users.user_id'), nullable=False),
            sa.Column('scma_id', sa.String(), nullable=True),
            sa.Column('active_hat', sa.String(), nullable=False),
            sa.Column('issued_at', sa.String(), nullable=False),
            sa.Column('last_activity_at', sa.String(), nullable=False),
            sa.Column('expires_at', sa.String(), nullable=False),
            sa.Column('idle_timeout_seconds', sa.Integer(), nullable=False, server_default='7200'),
            sa.Column('revoked_at', sa.String(), nullable=True),
            sa.Column('revoked_by', sa.String(), nullable=True),
        )
        op.create_index('ix_auth_sessions_user_id', 'auth_sessions', ['user_id'])
        op.create_index('ix_auth_sessions_scma_id', 'auth_sessions', ['scma_id'])
        op.create_index('ix_auth_sessions_active_hat', 'auth_sessions', ['active_hat'])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    for table_name in ('auth_sessions', 'auth_login_challenges', 'auth_users'):
        if table_name in existing:
            op.drop_table(table_name)
