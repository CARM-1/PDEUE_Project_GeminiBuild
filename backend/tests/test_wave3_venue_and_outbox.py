import asyncio

import pytest

from app.adapters.kalshi_client import KalshiClient
from app.adapters.polymarket_client import PolymarketClient
from app.adapters.rate_limiter import VenueRateLimiter
from app.domain.accounting_gateway import AccountingGateway
from app.domain.venue_router import VenueOrderDispatcher


def test_kalshi_client_normalizes_ladder_and_orderbook():
    client = KalshiClient(offline=True)
    ladder = client.normalize_ladder([{"ticker": "rain 50", "floor_strike": 12,
                                       "yes_bid": 40, "yes_ask": 43}])
    book = client.normalize_orderbook("rain 50", {"yes": [[40, 9]], "yes_asks": [[43, 4]]})
    assert ladder["interface_id"] == "IF-007"
    assert ladder["markets"][0]["ticker"] == "RAIN-50"
    assert book["best_bid_cents"] == 40 and book["best_ask_cents"] == 43


def test_polymarket_client_normalizes_clob_depth():
    book = PolymarketClient(offline=True).normalize_orderbook(
        "token-1", {"bids": [{"price": "0.41", "size": "7"}],
                    "asks": [{"price": "0.44", "size": "8"}]})
    assert book["bids"] == [{"price_cents": 41, "quantity": 7}]
    assert book["asks"] == [{"price_cents": 44, "quantity": 8}]


def test_venue_rate_limiter_throttles_rapid_requests():
    limiter = VenueRateLimiter({"TEST": {"rate": 100, "capacity": 1}})
    assert asyncio.run(limiter.acquire("TEST", timeout=.01))
    assert not asyncio.run(limiter.acquire("TEST", timeout=.001))


class RecordingClient:
    def __init__(self):
        self.payload = None

    async def place_order(self, payload):
        self.payload = payload
        return {"order_id": "ORDER-1", "status": "resting"}


def test_venue_order_dispatcher_enforces_strategy_d_maker_price():
    client = RecordingClient()
    dispatcher = VenueOrderDispatcher({"KALSHI": client}, available_capital_cents=10_000)
    routed = asyncio.run(dispatcher.dispatch({"venue": "KALSHI", "ticker": "RAIN", "bid_cents": 40,
                                              "ask_cents": 43, "quantity": 2}))
    assert routed["limit_price_cents"] == 41
    assert routed["post_only"] is True and routed["fee_cents"] == 0


def test_venue_order_dispatcher_respects_dry_powder_floor():
    dispatcher = VenueOrderDispatcher({"KALSHI": RecordingClient()}, available_capital_cents=5_000)
    result = asyncio.run(dispatcher.dispatch({"venue": "KALSHI", "ticker": "RAIN", "bid_cents": 50,
                                              "ask_cents": 60, "quantity": 21}))
    assert result["reason"] == "DRY_POWDER_FLOOR"


def _typed_payloads():
    timestamp = "2026-09-28T12:00:00+00:00"
    return [
        {"@context": "https://schema.pdeue.org/accounting/v1", "event_type": "DIVIDEND_DISTRIBUTION_SCHEDULED",
         "timestamp": timestamp, "scma_id": "SCMA-1", "amount_cents": 1, "tier": "GREEN",
         "destination_opaque_token": "EXT-REF-1"},
        {"@context": "https://schema.pdeue.org/accounting/v1", "event_type": "STABILITY_ADVANCE_FACILITY_REGISTERED",
         "facility_id": "FSAP-ADV-2026-0001", "timestamp": timestamp, "recipient_scma_id": "SCMA-1",
         "household_id": "HOUSE-1", "total_advance_cents": 100, "disbursement_plan": {
             "direct_creditor_payments": [], "initial_scma_seed_cents": 100}, "amortization_terms": {
             "interception_percentage": .5, "f2_discretionary_bounds": {"min_percentage": .3,
             "max_percentage": .7, "adjustment_lock_days": 30}, "recovery_target_cents": 100,
             "voluntary_pay_forward_eligible": True}, "governance_signatures": [
                 {"role": "F2_HEAD_OF_HOUSEHOLD", "actor_id": "F2", "signed_at": timestamp,
                  "signature_hmac_sha256": "a" * 64}, {"role": "CHIEF_ADMINISTRATOR", "actor_id": "CA",
                  "signed_at": timestamp, "signature_hmac_sha256": "b" * 64}]},
        {"@context": "https://schema.pdeue.org/accounting/v1", "event_type": "DIVIDEND_SWEEP_AMORTIZATION_APPLIED",
         "timestamp": timestamp, "facility_id": "FSAP-ADV-2026-0001", "scma_id": "SCMA-1",
         "total_sweep_cents": 10, "amortization_credit_cents": 5, "member_liquid_cents": 5,
         "remaining_advance_cents": 95},
        {"@context": "https://schema.pdeue.org/accounting/v1", "event_type": "CONTRIBUTOR_INCENTIVE_HARVESTED",
         "timestamp": timestamp, "contributor_scma_id": "SCMA-1", "pool_income_cents": 100,
         "time_weighted_share_bps": 100, "incentive_amount_cents": 1},
    ]


def test_accounting_outbox_signs_and_verifies_if_038_through_if_041():
    gateway = AccountingGateway("tenant-test-secret")
    events = [method(payload) for method, payload in zip(
        (gateway.stage_if038_event, gateway.stage_if039_event,
         gateway.stage_if040_event, gateway.stage_if041_event), _typed_payloads())]
    assert [event["sequence_id"] for event in events] == [1, 2, 3, 4]
    assert all(gateway.verify_event(event) and len(event["signature_hmac_sha256"]) == 64 for event in events)


def test_capital_sweep_emits_event_when_balance_exceeds_threshold():
    event = AccountingGateway("tenant-test-secret").emit_capital_sweep(2_500_101)
    assert event["event_type"] == "CAPITAL_SWEEP"
    assert event["payload"]["amount_cents"] == 101


def test_zero_banking_credentials_in_outbox_payloads():
    gateway = AccountingGateway("tenant-test-secret")
    payload = _typed_payloads()[0]
    payload["routing_number"] = "prohibited"
    with pytest.raises(ValueError, match="banking credentials"):
        gateway.stage_event(payload)
