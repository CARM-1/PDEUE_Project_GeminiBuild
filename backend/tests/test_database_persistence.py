import hashlib
import json
import pytest
from sqlalchemy.exc import IntegrityError
from app.db.session import Base, engine, SessionLocal
from app.db.models import (
    TenantModel,
    PrincipalModel,
    EventRecordModel,
    EvidenceItemModel,
    DecisionPacketRecordModel,
    OrderRecordModel,
    FillRecordModel,
    PositionRecordModel,
    AuditLogRecordModel
)

@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_tenant_and_principal_cascade():
    db = SessionLocal()
    tenant = TenantModel(tenant_id='TENANT-01', name='Alpha Desk')
    db.add(tenant)
    db.commit()

    principal = PrincipalModel(principal_id='USR-01', tenant_id='TENANT-01', role='RISK_OFFICER')
    db.add(principal)
    db.commit()

    queried = db.query(TenantModel).filter(TenantModel.tenant_id == 'TENANT-01').first()
    assert queried is not None
    assert len(queried.principals) == 1
    assert queried.principals[0].role == 'RISK_OFFICER'

    db.delete(queried)
    db.commit()
    assert db.query(PrincipalModel).filter(PrincipalModel.principal_id == 'USR-01').first() is None
    db.close()

def test_event_and_evidence_persistence():
    db = SessionLocal()
    event = EventRecordModel(
        event_id='EVT-WX-DB-01',
        domain='WEATHER',
        title='Chicago High Above 75F',
        resolution_source='NOAA_NWS_KORD',
        cutoff_timestamp='2026-09-03T12:00:00Z'
    )
    evidence = EvidenceItemModel(
        evidence_id='EVD-01',
        event_id='EVT-WX-DB-01',
        source='NOAA_ASOS',
        published_at='2026-09-03T11:45:00Z',
        payload_json=json.dumps({'temp_c': 24.2})
    )
    db.add(event)
    db.add(evidence)
    db.commit()

    ev = db.query(EventRecordModel).filter(EventRecordModel.event_id == 'EVT-WX-DB-01').first()
    assert ev is not None
    assert len(ev.evidence_items) == 1
    assert '24.2' in ev.evidence_items[0].payload_json
    db.close()

def test_order_and_fill_with_idempotency_constraint():
    db = SessionLocal()
    order = OrderRecordModel(
        order_id='ORD-DB-001',
        tenant_id='TENANT-01',
        contract_id='KX-HIGH-75',
        venue='KALSHI',
        side='BUY',
        price=0.55,
        quantity=100,
        status='ROUTED',
        idempotency_key='IDEM-KEY-999'
    )
    db.add(order)
    db.commit()

    fill = FillRecordModel(fill_id='FILL-001', order_id='ORD-DB-001', fill_price=0.55, fill_quantity=100)
    db.add(fill)
    db.commit()

    duplicate_order = OrderRecordModel(
        order_id='ORD-DB-002',
        tenant_id='TENANT-01',
        contract_id='KX-HIGH-75',
        venue='KALSHI',
        side='BUY',
        price=0.55,
        quantity=100,
        status='ROUTED',
        idempotency_key='IDEM-KEY-999'
    )
    db.add(duplicate_order)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.close()

def test_audit_log_hash_chain():
    db = SessionLocal()
    genesis_prev = '0' * 64
    payload1 = 'ACTION_INIT'
    hash1 = hashlib.sha256(f'{genesis_prev}:{payload1}'.encode()).hexdigest()
    entry1 = AuditLogRecordModel(
        entry_id='AUD-01',
        tenant_id='TENANT-01',
        actor_id='CHIEF_ADMIN',
        action='INITIALIZE',
        prev_hash=genesis_prev,
        entry_hash=hash1,
        payload=payload1
    )
    db.add(entry1)
    db.commit()

    payload2 = 'RESERVATION_ALLOCATED'
    hash2 = hashlib.sha256(f'{hash1}:{payload2}'.encode()).hexdigest()
    entry2 = AuditLogRecordModel(
        entry_id='AUD-02',
        tenant_id='TENANT-01',
        actor_id='SYSTEM_LEDGER',
        action='RESERVE',
        prev_hash=hash1,
        entry_hash=hash2,
        payload=payload2
    )
    db.add(entry2)
    db.commit()

    entries = db.query(AuditLogRecordModel).order_by(AuditLogRecordModel.recorded_at).all()
    assert len(entries) == 2
    assert entries[1].prev_hash == entries[0].entry_hash
    db.close()
