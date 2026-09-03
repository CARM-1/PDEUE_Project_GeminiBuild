from app.domain.multi_venue_coordinator import MultiVenueCoordinator
from app.db.session import Base, engine, SessionLocal
from app.db.models import DecisionPacketRecordModel, OrderRecordModel

def test_multi_venue_coordinator_kalshi_flow():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    coordinator = MultiVenueCoordinator(db_session=db)
    raw_kalshi = [
        {'ticker': 'KX-ORD-20', 'strike_val': 20.0, 'yes_bid': 0.95, 'yes_ask': 0.99},
        {'ticker': 'KX-ORD-26', 'strike_val': 26.0, 'yes_bid': 0.08, 'yes_ask': 0.12}
    ]
    res = coordinator.process_and_dispatch_ladder(
        tenant_id='tenant_multi',
        account_id='acc_multi_01',
        venue='KALSHI',
        category='WEATHER',
        raw_ladder=raw_kalshi,
        ensemble_members=[24.0, 24.5, 25.0, 25.5, 25.0],
        event_id='EVT-MULTI-01',
        station_id='KORD'
    )
    assert res['venue'] == 'KALSHI'
    assert res['normalized_contracts_count'] == 2
    assert res['dispatch_result']['status'] == 'DISPATCHED'
    assert res['persisted'] is True
    saved_pkt = db.query(DecisionPacketRecordModel).filter_by(tenant_id='tenant_multi').first()
    saved_ord = db.query(OrderRecordModel).filter_by(tenant_id='tenant_multi').first()
    assert saved_pkt is not None
    assert saved_ord is not None
    assert saved_ord.venue == 'KALSHI'
    db.close()

def test_multi_venue_coordinator_polymarket_flow():
    coordinator = MultiVenueCoordinator(db_session=None)
    raw_poly = [
        {'token_id': 'POLY-ORD-26', 'strike_value': 26.0, 'price_bid': 0.08, 'price_ask': 0.12}
    ]
    res = coordinator.process_and_dispatch_ladder(
        tenant_id='tenant_poly',
        account_id='acc_poly_01',
        venue='POLYMARKET',
        category='WEATHER',
        raw_ladder=raw_poly,
        ensemble_members=[24.0, 24.5, 25.0, 25.5, 25.0],
        event_id='EVT-MULTI-02',
        station_id='KORD'
    )
    assert res['venue'] == 'POLYMARKET'
    assert res['dispatch_result']['status'] == 'DISPATCHED'
    assert res['persisted'] is False
