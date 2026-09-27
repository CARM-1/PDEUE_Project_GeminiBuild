from app.domain.accounting_gateway import AccountingGateway
from app.domain.capital_ledger import CapitalLedger
from app.domain.position_book import PositionBook
from app.domain.priority_eviction import PriorityEvictionManager
from app.domain.settlement_engine import SettlementReconciler
from app.domain.sweep_daemon import FloatSweepMonitor


def test_n12_concurrency_saturation_and_eviction():
    manager = PriorityEvictionManager()
    for index in range(12):
        manager.register_resting_order(
            candidate_id=f'candidate-{index}', ticker=f'C-{index}', domain='TEST',
            edge=0.05 + index / 1000, amount_cents=500,
        )
    decision = manager.evaluate_preemption(
        {'net_edge': 0.25, 'proposed_stake_cents': 500, 'expiry_hours': 1},
        total_equity_cents=10_000, currently_committed_cents=6_000,
    )
    assert decision['reason'] == 'PREEMPTION_APPROVED'
    assert decision['eviction_target']['candidate_id'] == 'candidate-0'
    manager.execute_eviction('candidate-0')
    assert len(manager.resting_orders) == 11


def test_dry_powder_floor_enforced_at_12_slots():
    manager = PriorityEvictionManager()
    for index in range(12):
        manager.register_resting_order(
            candidate_id=f'candidate-{index}', ticker=f'C-{index}', domain='TEST',
            edge=0.05, amount_cents=500,
        )
    decision = manager.evaluate_preemption(
        {'net_edge': 0.30, 'proposed_stake_cents': 501, 'expiry_hours': 1},
        total_equity_cents=10_000, currently_committed_cents=6_000,
    )
    assert decision == {
        'admitted': False,
        'reason': 'DRY_POWDER_FLOOR_ENFORCED',
        'eviction_target': None,
    }


def test_complete_set_instant_recycling():
    ledger = CapitalLedger(initial_balance_cents=0)
    ledger.register_member_account('SCMA-1', 0)
    book = PositionBook()
    reconciler = SettlementReconciler(position_book=book, ledger=ledger)
    reconciler.process_fill('SCMA-1', 'CONTRACT-1', 'VENUE', 'TEST', 'BUY_YES', 0.4, 10, 400)
    result = reconciler.process_fill('SCMA-1', 'CONTRACT-1', 'VENUE', 'TEST', 'BUY_NO', 0.5, 7, 350)
    assert result['released_cents'] == 700
    assert ledger.members['SCMA-1']['balance_cents'] == 700
    remaining = list(book.positions.values())
    assert len(remaining) == 1
    assert remaining[0]['outcome_side'] == 'YES'
    assert remaining[0]['quantity'] == 3


def test_25k_float_high_watermark_sweep():
    ledger = CapitalLedger(initial_balance_cents=2_575_125)
    gateway = AccountingGateway(secret_key='test-sweep-key')
    event = FloatSweepMonitor().scan_and_sweep('MASTER', ledger, gateway)
    assert ledger.balance_cents == 2_500_000
    assert event['payload']['amount_cents'] == 75_125
    assert event['payload']['source'] == 'FLOAT_CAP_SWEEP'
    canonical = gateway._canonicalize_payload(event['payload'])
    assert gateway.verify_signature(canonical, event['signature_hmac_sha256'])
