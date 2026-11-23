"""Add ADR-012 per-SCMA high_water_mark_cents column to accounts table."""
revision = '002_add_account_high_water_mark'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'accounts' in inspector.get_table_names():
        columns = {col['name'] for col in inspector.get_columns('accounts')}
        if 'high_water_mark_cents' not in columns:
            op.add_column(
                'accounts',
                sa.Column(
                    'high_water_mark_cents',
                    sa.BigInteger(),
                    nullable=False,
                    server_default='0',
                ),
            )
            op.execute(
                sa.text(
                    'UPDATE accounts SET high_water_mark_cents = COALESCE(balance_cents, 0)'
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'accounts' in inspector.get_table_names():
        columns = {col['name'] for col in inspector.get_columns('accounts')}
        if 'high_water_mark_cents' in columns:
            with op.batch_alter_table('accounts') as batch_op:
                batch_op.drop_column('high_water_mark_cents')
