import os
import pathlib
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect

def test_alembic_upgrade_and_downgrade():
    here = pathlib.Path(__file__).resolve()
    backend_dir = here.parents[1]
    ini_path = backend_dir / 'alembic.ini'
    test_db = backend_dir / 'test_migration.db'
    if test_db.exists():
        test_db.unlink()
    db_url = f'sqlite:///{test_db.as_posix()}'

    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option('script_location', str(backend_dir / 'alembic'))
    alembic_cfg.set_main_option('sqlalchemy.url', db_url)

    command.upgrade(alembic_cfg, 'head')
    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert 'accounting_outbox_events' in tables, 'Outbox table not created by migration'

    command.downgrade(alembic_cfg, 'base')
    inspector_down = inspect(engine)
    tables_down = inspector_down.get_table_names()
    assert 'accounting_outbox_events' not in tables_down, 'Outbox table not dropped on downgrade'

    if test_db.exists():
        test_db.unlink()
