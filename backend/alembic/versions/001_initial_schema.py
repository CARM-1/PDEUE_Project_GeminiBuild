revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    op.create_table('accounting_outbox_events',
        sa.Column('event_id', sa.String(), primary_key=True),
        sa.Column('sequence_id', sa.Integer(), nullable=False, unique=True),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.Column('signature_hmac_sha256', sa.String(), nullable=False),
        sa.Column('status', sa.String(), default='EMITTED'),
        sa.Column('created_at', sa.String(), nullable=False)
    )

def downgrade() -> None:
    op.drop_table('accounting_outbox_events')
