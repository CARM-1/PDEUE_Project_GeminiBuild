"""Add PR #82 Hall of Arms heritage profiles, surname records, and isolated community notifications."""
revision = '006_add_heritage_hall_of_arms_and_notifications'
down_revision = '005_add_role_provisioning_custody_delegation'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if 'heritage_house_profiles' not in existing:
        op.create_table(
            'heritage_house_profiles',
            sa.Column('house_id', sa.Integer(), primary_key=True),
            sa.Column('lineage_code', sa.String(), nullable=False, unique=True),
            sa.Column('house_name', sa.String(), nullable=False),
            sa.Column('motto', sa.String(), nullable=False),
            sa.Column('crest_asset_path', sa.String(), nullable=False),
            sa.Column('founding_branch', sa.String(), nullable=False, server_default='Carmichael — McCormick'),
            sa.Column('history_body', sa.Text(), nullable=False),
            sa.Column('milestones_json', sa.Text(), nullable=False, server_default='[]'),
            sa.Column('updated_by', sa.String(), nullable=False, server_default='SYSTEM_SEED'),
            sa.Column('updated_at_utc', sa.String(), nullable=False),
        )
        op.create_index('ix_heritage_house_profiles_lineage_code', 'heritage_house_profiles', ['lineage_code'])

    if 'heritage_surname_records' not in existing:
        op.create_table(
            'heritage_surname_records',
            sa.Column('slug', sa.String(), primary_key=True),
            sa.Column('surname', sa.String(), nullable=False),
            sa.Column('is_founding', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('house_id', sa.Integer(), sa.ForeignKey('heritage_house_profiles.house_id'), nullable=False),
            sa.Column('crest_asset_path', sa.String(), nullable=False),
            sa.Column('origin_summary', sa.String(), nullable=False),
            sa.Column('history_body', sa.Text(), nullable=False),
            sa.Column('updated_by', sa.String(), nullable=False, server_default='SYSTEM_SEED'),
            sa.Column('updated_at_utc', sa.String(), nullable=False),
        )
        op.create_index('ix_heritage_surname_records_surname', 'heritage_surname_records', ['surname'])
        op.create_index('ix_heritage_surname_records_house_id', 'heritage_surname_records', ['house_id'])

    if 'community_notifications' not in existing:
        op.create_table(
            'community_notifications',
            sa.Column('notification_id', sa.String(), primary_key=True),
            sa.Column('category', sa.String(), nullable=False, server_default='ANNOUNCEMENT'),
            sa.Column('title', sa.String(), nullable=False),
            sa.Column('message', sa.Text(), nullable=False),
            sa.Column('target_scope', sa.String(), nullable=False, server_default='ALL_FAMILY'),
            sa.Column('target_house_id', sa.Integer(), nullable=True),
            sa.Column('action_url', sa.String(), nullable=False, server_default='/community'),
            sa.Column('sender_id', sa.String(), nullable=False, server_default='SYSTEM'),
            sa.Column('sender_role', sa.String(), nullable=False, server_default='CHIEF_ADMIN'),
            sa.Column('channels_json', sa.Text(), nullable=False, server_default='["in_app"]'),
            sa.Column('delivery_audit_json', sa.Text(), nullable=False, server_default='[]'),
            sa.Column('r12_sanitized', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('created_at_utc', sa.String(), nullable=False),
        )
        op.create_index('ix_community_notifications_category', 'community_notifications', ['category'])
        op.create_index('ix_community_notifications_target_house_id', 'community_notifications', ['target_house_id'])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    for table_name in (
        'community_notifications',
        'heritage_surname_records',
        'heritage_house_profiles',
    ):
        if table_name in existing:
            op.drop_table(table_name)
