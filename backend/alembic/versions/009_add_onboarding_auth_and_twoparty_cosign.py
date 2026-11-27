"""Add PR #99 onboarding allowlist email & two-party admission co-sign columns."""
revision = '009_add_onboarding_auth_and_twoparty_cosign'
down_revision = '008_add_session_auth_tables'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def _existing_columns(inspector, table_name: str) -> set[str]:
    if table_name not in inspector.get_table_names():
        return set()
    return {col['name'] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    onb_cols = _existing_columns(inspector, 'onboarding_members')
    if onb_cols and 'email' not in onb_cols:
        op.add_column('onboarding_members', sa.Column('email', sa.String(), nullable=True))

    policy_cols = _existing_columns(inspector, 'enclave_policy_controls')
    if policy_cols and 'admission_authority_mode' not in policy_cols:
        op.add_column(
            'enclave_policy_controls',
            sa.Column(
                'admission_authority_mode',
                sa.String(),
                nullable=False,
                server_default='CHIEF_ADMIN_SOLO',
            ),
        )

    dossier_cols = _existing_columns(inspector, 'delegated_onboarding_dossiers')
    if dossier_cols:
        additions = (
            ('applicant_email', sa.String(), None),
            ('f2h_cosigned_by', sa.String(), None),
            ('f2h_cosigned_role', sa.String(), None),
            ('f2h_cosigned_house_id', sa.Integer(), None),
            ('f2h_cosigned_at_utc', sa.String(), None),
            ('f2h_cosign_notes', sa.Text(), ''),
            ('f2h_cosign_signature', sa.String(), None),
        )
        for col_name, col_type, default_val in additions:
            if col_name not in dossier_cols:
                op.add_column(
                    'delegated_onboarding_dossiers',
                    sa.Column(col_name, col_type, nullable=True, server_default=default_val),
                )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    dossier_cols = _existing_columns(inspector, 'delegated_onboarding_dossiers')
    if dossier_cols:
        with op.batch_alter_table('delegated_onboarding_dossiers') as batch_op:
            for col_name in (
                'f2h_cosign_signature',
                'f2h_cosign_notes',
                'f2h_cosigned_at_utc',
                'f2h_cosigned_house_id',
                'f2h_cosigned_role',
                'f2h_cosigned_by',
                'applicant_email',
            ):
                if col_name in dossier_cols:
                    batch_op.drop_column(col_name)

    policy_cols = _existing_columns(inspector, 'enclave_policy_controls')
    if policy_cols and 'admission_authority_mode' in policy_cols:
        with op.batch_alter_table('enclave_policy_controls') as batch_op:
            batch_op.drop_column('admission_authority_mode')

    onb_cols = _existing_columns(inspector, 'onboarding_members')
    if onb_cols and 'email' in onb_cols:
        with op.batch_alter_table('onboarding_members') as batch_op:
            batch_op.drop_column('email')
