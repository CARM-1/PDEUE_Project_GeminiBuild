"""Add Milestone C1 member onboarding and 48-hour single-use invite token tables."""
revision = '003_add_member_onboarding_tables'
down_revision = '002_add_account_high_water_mark'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if 'onboarding_members' not in existing:
        op.create_table(
            'onboarding_members',
            sa.Column('member_id', sa.String(), primary_key=True),
            sa.Column('scma_id', sa.String(), nullable=False, unique=True),
            sa.Column('full_name', sa.String(), nullable=False),
            sa.Column('house_id', sa.Integer(), nullable=False),
            sa.Column('lineage_code', sa.String(), nullable=False),
            sa.Column('role_tier', sa.String(), nullable=False, server_default='MEMBER_USER'),
            sa.Column('seed_cents', sa.BigInteger(), nullable=False),
            sa.Column('high_water_mark_cents', sa.BigInteger(), nullable=False),
            sa.Column('risk_dial_bps', sa.Integer(), nullable=False, server_default='150'),
            sa.Column('is_custodial', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('bank_ref_token', sa.String(), nullable=False),
            sa.Column('status', sa.String(), nullable=False, server_default='PENDING_TUTOR_CERTIFICATION'),
            sa.Column('certification_level', sa.String(), nullable=True),
            sa.Column('certified_at', sa.String(), nullable=True),
            sa.Column('invite_activated_at', sa.String(), nullable=True),
            sa.Column('created_by', sa.String(), nullable=False, server_default='CHIEF_ADMINISTRATOR'),
            sa.Column('created_at', sa.String(), nullable=False),
        )

    if 'onboarding_invite_tokens' not in existing:
        op.create_table(
            'onboarding_invite_tokens',
            sa.Column('token_hash', sa.String(), primary_key=True),
            sa.Column('token_prefix', sa.String(), nullable=False),
            sa.Column('member_id', sa.String(), sa.ForeignKey('onboarding_members.member_id'), nullable=False),
            sa.Column('scma_id', sa.String(), nullable=False),
            sa.Column('expires_at', sa.String(), nullable=False),
            sa.Column('consumed_at', sa.String(), nullable=True),
            sa.Column('created_at', sa.String(), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    if 'onboarding_invite_tokens' in existing:
        op.drop_table('onboarding_invite_tokens')
    if 'onboarding_members' in existing:
        op.drop_table('onboarding_members')
