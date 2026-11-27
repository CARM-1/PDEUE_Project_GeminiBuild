"""Add PR #97 normalized Family Tree people and relationships tables."""
revision = '007_add_family_tree_tables'
down_revision = '006_add_heritage_hall_of_arms_and_notifications'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if 'family_tree_people' not in existing:
        op.create_table(
            'family_tree_people',
            sa.Column('person_id', sa.String(), primary_key=True),
            sa.Column('full_name', sa.String(), nullable=False),
            sa.Column('given_name', sa.String(), nullable=False, server_default=''),
            sa.Column('surname', sa.String(), nullable=False, server_default=''),
            sa.Column('suffix', sa.String(), nullable=False, server_default=''),
            sa.Column('nickname', sa.String(), nullable=False, server_default=''),
            sa.Column('house_id', sa.String(), nullable=False, server_default='FOUNDERS'),
            sa.Column('generation', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('is_deceased', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('birth_year', sa.Integer(), nullable=True),
            sa.Column('death_year', sa.Integer(), nullable=True),
            sa.Column('bio_notes', sa.Text(), nullable=False, server_default=''),
            sa.Column('source_tag', sa.String(), nullable=False, server_default='SEED_V1'),
            sa.Column('review_flag', sa.String(), nullable=False, server_default=''),
            sa.Column('is_reference_branch', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('updated_by', sa.String(), nullable=False, server_default='SYSTEM_SEED'),
            sa.Column('updated_at_utc', sa.String(), nullable=False),
        )
        op.create_index('ix_family_tree_people_full_name', 'family_tree_people', ['full_name'])
        op.create_index('ix_family_tree_people_surname', 'family_tree_people', ['surname'])
        op.create_index('ix_family_tree_people_house_id', 'family_tree_people', ['house_id'])
        op.create_index('ix_family_tree_people_generation', 'family_tree_people', ['generation'])
        op.create_index('ix_family_tree_people_is_reference_branch', 'family_tree_people', ['is_reference_branch'])

    if 'family_tree_relationships' not in existing:
        op.create_table(
            'family_tree_relationships',
            sa.Column('rel_id', sa.String(), primary_key=True),
            sa.Column('rel_type', sa.String(), nullable=False),
            sa.Column('person_a_id', sa.String(), sa.ForeignKey('family_tree_people.person_id'), nullable=False),
            sa.Column('person_b_id', sa.String(), sa.ForeignKey('family_tree_people.person_id'), nullable=False),
            sa.Column('notes', sa.Text(), nullable=False, server_default=''),
            sa.Column('source_tag', sa.String(), nullable=False, server_default='SEED_V1'),
            sa.Column('updated_by', sa.String(), nullable=False, server_default='SYSTEM_SEED'),
            sa.Column('updated_at_utc', sa.String(), nullable=False),
        )
        op.create_index('ix_family_tree_relationships_rel_type', 'family_tree_relationships', ['rel_type'])
        op.create_index('ix_family_tree_relationships_person_a_id', 'family_tree_relationships', ['person_a_id'])
        op.create_index('ix_family_tree_relationships_person_b_id', 'family_tree_relationships', ['person_b_id'])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    for table_name in ('family_tree_relationships', 'family_tree_people'):
        if table_name in existing:
            op.drop_table(table_name)
