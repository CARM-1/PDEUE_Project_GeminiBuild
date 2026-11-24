"""Add PR #81 role provisioning, custodial anti-tribalism, and delegated onboarding tables."""
revision = '005_add_role_provisioning_custody_delegation'
down_revision = '004_add_12_house_lineage_governance'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if 'user_role_assignments' not in existing:
        op.create_table(
            'user_role_assignments',
            sa.Column('assignment_id', sa.String(), primary_key=True),
            sa.Column('member_id', sa.String(), nullable=False),
            sa.Column('role_token', sa.String(), nullable=False),
            sa.Column('house_id', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(), nullable=False, server_default='ACTIVE'),
            sa.Column('assigned_by', sa.String(), nullable=False, server_default='CHIEF_ADMINISTRATOR'),
            sa.Column('assigned_at_utc', sa.String(), nullable=False),
            sa.Column('revoked_at_utc', sa.String(), nullable=True),
            sa.Column('reason', sa.Text(), nullable=True, server_default=''),
        )
        op.create_index('ix_user_role_assignments_member_id', 'user_role_assignments', ['member_id'])
        op.create_index('ix_user_role_assignments_role_token', 'user_role_assignments', ['role_token'])
        op.create_index('ix_user_role_assignments_status', 'user_role_assignments', ['status'])

    if 'custodial_assignments' not in existing:
        op.create_table(
            'custodial_assignments',
            sa.Column('custody_id', sa.String(), primary_key=True),
            sa.Column('custodian_member_id', sa.String(), nullable=False),
            sa.Column('custodian_role', sa.String(), nullable=False),
            sa.Column('charge_member_id', sa.String(), nullable=False),
            sa.Column('charge_scma_id', sa.String(), nullable=False),
            sa.Column('charge_house_id', sa.Integer(), nullable=False),
            sa.Column('assignment_mode', sa.String(), nullable=False, server_default='INTRA_HOUSE'),
            sa.Column('active', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('assigned_by', sa.String(), nullable=False, server_default='SYSTEM_INIT'),
            sa.Column('assigned_at_utc', sa.String(), nullable=False),
            sa.Column('ended_at_utc', sa.String(), nullable=True),
            sa.Column('reason', sa.Text(), nullable=True, server_default=''),
        )
        op.create_index('ix_custodial_assignments_custodian_member_id', 'custodial_assignments', ['custodian_member_id'])
        op.create_index('ix_custodial_assignments_charge_member_id', 'custodial_assignments', ['charge_member_id'])
        op.create_index('ix_custodial_assignments_charge_scma_id', 'custodial_assignments', ['charge_scma_id'])
        op.create_index('ix_custodial_assignments_active', 'custodial_assignments', ['active'])

    if 'enclave_policy_controls' not in existing:
        op.create_table(
            'enclave_policy_controls',
            sa.Column('config_id', sa.String(), primary_key=True),
            sa.Column('custody_assignment_mode', sa.String(), nullable=False, server_default='INTRA_HOUSE'),
            sa.Column('delegated_onboarding_scope', sa.String(), nullable=False, server_default='ADMIN_ONLY'),
            sa.Column('genealogical_board_enabled', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('genealogical_board_quorum', sa.Integer(), nullable=False, server_default='2'),
            sa.Column('house_delegation_flags_json', sa.Text(), nullable=False, server_default='{}'),
            sa.Column('updated_by', sa.String(), nullable=False, server_default='SYSTEM_INIT'),
            sa.Column('updated_at_utc', sa.String(), nullable=False),
            sa.Column('reason', sa.Text(), nullable=True, server_default=''),
        )

    if 'delegated_onboarding_dossiers' not in existing:
        op.create_table(
            'delegated_onboarding_dossiers',
            sa.Column('dossier_id', sa.String(), primary_key=True),
            sa.Column('applicant_full_name', sa.String(), nullable=False),
            sa.Column('applicant_member_id', sa.String(), nullable=True),
            sa.Column('target_house_id', sa.Integer(), nullable=False),
            sa.Column('lineage_code', sa.String(), nullable=False),
            sa.Column('kinship_verification', sa.Text(), nullable=False),
            sa.Column('custodial_status', sa.String(), nullable=False, server_default='ADULT'),
            sa.Column('is_custodial', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('pay_it_forward_sponsored', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('sponsor_member_id', sa.String(), nullable=True),
            sa.Column('seed_cents', sa.BigInteger(), nullable=False, server_default='0'),
            sa.Column('risk_dial_bps', sa.Integer(), nullable=False, server_default='150'),
            sa.Column('bank_ref_token', sa.String(), nullable=False),
            sa.Column('due_diligence_attestation', sa.Text(), nullable=False),
            sa.Column('attestation_signature', sa.String(), nullable=False),
            sa.Column('submitted_by_member_id', sa.String(), nullable=False),
            sa.Column('submitted_by_role', sa.String(), nullable=False),
            sa.Column('submitted_by_house_id', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(), nullable=False, server_default='PENDING_RATIFICATION'),
            sa.Column('board_votes_json', sa.Text(), nullable=False, server_default='[]'),
            sa.Column('ratified_by', sa.String(), nullable=True),
            sa.Column('ratified_at_utc', sa.String(), nullable=True),
            sa.Column('decision_notes', sa.Text(), nullable=True, server_default=''),
            sa.Column('provisioned_member_id', sa.String(), nullable=True),
            sa.Column('provisioned_scma_id', sa.String(), nullable=True),
            sa.Column('assigned_custodian_member_id', sa.String(), nullable=True),
            sa.Column('ifas_outbox_event_id', sa.String(), nullable=True),
            sa.Column('created_at_utc', sa.String(), nullable=False),
            sa.Column('updated_at_utc', sa.String(), nullable=False),
        )
        op.create_index('ix_delegated_onboarding_dossiers_status', 'delegated_onboarding_dossiers', ['status'])
        op.create_index('ix_delegated_onboarding_dossiers_target_house_id', 'delegated_onboarding_dossiers', ['target_house_id'])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    for table_name in (
        'delegated_onboarding_dossiers',
        'enclave_policy_controls',
        'custodial_assignments',
        'user_role_assignments',
    ):
        if table_name in existing:
            op.drop_table(table_name)
