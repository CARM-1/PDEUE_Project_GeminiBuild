"""Add Milestone C6 12-House lineage and configurable enclave governance tables."""
revision = '004_add_12_house_lineage_governance'
down_revision = '003_add_member_onboarding_tables'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if 'lineage_houses' not in existing:
        op.create_table(
            'lineage_houses',
            sa.Column('house_id', sa.Integer(), primary_key=True),
            sa.Column('lineage_code', sa.String(), nullable=False, unique=True),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('leader_name', sa.String(), nullable=False),
            sa.Column('leader_role', sa.String(), nullable=False, server_default='H2'),
            sa.Column('status', sa.String(), nullable=False, server_default='ACTIVE'),
            sa.Column('governance_seat', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('created_at', sa.String(), nullable=False),
            sa.Column('updated_at', sa.String(), nullable=False),
        )

    if 'lineage_house_members' not in existing:
        op.create_table(
            'lineage_house_members',
            sa.Column('scma_id', sa.String(), primary_key=True),
            sa.Column('house_id', sa.Integer(), sa.ForeignKey('lineage_houses.house_id'), nullable=False),
            sa.Column('member_id', sa.String(), nullable=True),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('role_tag', sa.String(), nullable=False, server_default='Lineal Member'),
            sa.Column('cash_cents', sa.BigInteger(), nullable=False, server_default='0'),
            sa.Column('high_water_mark_cents', sa.BigInteger(), nullable=False, server_default='0'),
            sa.Column('risk_dial_bps', sa.Integer(), nullable=False, server_default='100'),
            sa.Column('baseline_risk_dial_bps', sa.Integer(), nullable=False, server_default='100'),
            sa.Column('is_custodial', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('status', sa.String(), nullable=False, server_default='ACTIVE'),
            sa.Column('literacy_completion_pct', sa.Integer(), nullable=False, server_default='100'),
            sa.Column('open_orders_json', sa.Text(), nullable=False, server_default='[]'),
            sa.Column('created_at', sa.String(), nullable=False),
            sa.Column('updated_at', sa.String(), nullable=False),
        )

    if 'governance_config' not in existing:
        op.create_table(
            'governance_config',
            sa.Column('config_id', sa.String(), primary_key=True),
            sa.Column('governance_mode', sa.String(), nullable=False, server_default='EXECUTIVE_COMMAND'),
            sa.Column('updated_by', sa.String(), nullable=False, server_default='SYSTEM_INIT'),
            sa.Column('updated_at', sa.String(), nullable=False),
            sa.Column('last_reason', sa.Text(), nullable=True),
        )

    if 'governance_bodies' not in existing:
        op.create_table(
            'governance_bodies',
            sa.Column('body_id', sa.String(), primary_key=True),
            sa.Column('name', sa.String(), nullable=False, unique=True),
            sa.Column('description', sa.Text(), nullable=False, server_default=''),
            sa.Column('quorum_numerator', sa.Integer(), nullable=False, server_default='9'),
            sa.Column('quorum_denominator', sa.Integer(), nullable=False, server_default='12'),
            sa.Column('quorum_pct', sa.Integer(), nullable=False, server_default='75'),
            sa.Column('veto_threshold_count', sa.Integer(), nullable=False, server_default='9'),
            sa.Column('veto_threshold_pct', sa.Integer(), nullable=False, server_default='75'),
            sa.Column('can_exercise_stage3_veto', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('active', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('created_by', sa.String(), nullable=False, server_default='CHIEF_ADMINISTRATOR'),
            sa.Column('created_at', sa.String(), nullable=False),
            sa.Column('updated_at', sa.String(), nullable=False),
        )

    if 'governance_voter_seats' not in existing:
        op.create_table(
            'governance_voter_seats',
            sa.Column('seat_id', sa.String(), primary_key=True),
            sa.Column('body_id', sa.String(), sa.ForeignKey('governance_bodies.body_id'), nullable=False),
            sa.Column('seat_type', sa.String(), nullable=False, server_default='HOUSE_OFFICE'),
            sa.Column('house_id', sa.Integer(), nullable=True),
            sa.Column('office_role', sa.String(), nullable=True),
            sa.Column('user_id', sa.String(), nullable=True),
            sa.Column('display_name', sa.String(), nullable=False),
            sa.Column('can_vote', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('can_veto', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('active', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('granted_by', sa.String(), nullable=False, server_default='CHIEF_ADMINISTRATOR'),
            sa.Column('granted_at', sa.String(), nullable=False),
            sa.Column('revoked_by', sa.String(), nullable=True),
            sa.Column('revoked_at', sa.String(), nullable=True),
        )

    if 'governance_petitions' not in existing:
        op.create_table(
            'governance_petitions',
            sa.Column('proposal_id', sa.String(), primary_key=True),
            sa.Column('body_id', sa.String(), sa.ForeignKey('governance_bodies.body_id'), nullable=False),
            sa.Column('title', sa.String(), nullable=False),
            sa.Column('description', sa.Text(), nullable=False, server_default=''),
            sa.Column('proposal_category', sa.String(), nullable=False, server_default='CFCP_GRANT'),
            sa.Column('target_house_id', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('amount_cents', sa.BigInteger(), nullable=False, server_default='0'),
            sa.Column('status', sa.String(), nullable=False, server_default='HOUSE_VOTE_OPEN'),
            sa.Column('created_by', sa.String(), nullable=False, server_default='SYSTEM'),
            sa.Column('settled_by', sa.String(), nullable=True),
            sa.Column('settled_at', sa.String(), nullable=True),
            sa.Column('veto_reason', sa.Text(), nullable=True),
            sa.Column('created_at', sa.String(), nullable=False),
            sa.Column('updated_at', sa.String(), nullable=False),
        )

    if 'governance_votes' not in existing:
        op.create_table(
            'governance_votes',
            sa.Column('vote_id', sa.String(), primary_key=True),
            sa.Column('proposal_id', sa.String(), sa.ForeignKey('governance_petitions.proposal_id'), nullable=False),
            sa.Column('body_id', sa.String(), sa.ForeignKey('governance_bodies.body_id'), nullable=False),
            sa.Column('seat_id', sa.String(), sa.ForeignKey('governance_voter_seats.seat_id'), nullable=True),
            sa.Column('voter_house_id', sa.Integer(), nullable=True),
            sa.Column('voter_user_id', sa.String(), nullable=True),
            sa.Column('voter_display_name', sa.String(), nullable=False),
            sa.Column('vote_choice', sa.String(), nullable=False),
            sa.Column('rationale', sa.Text(), nullable=True, server_default=''),
            sa.Column('cast_at', sa.String(), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    for table_name in (
        'governance_votes',
        'governance_petitions',
        'governance_voter_seats',
        'governance_bodies',
        'governance_config',
        'lineage_house_members',
        'lineage_houses',
    ):
        if table_name in existing:
            op.drop_table(table_name)
