from app.domain.event_queue import EventIngestionQueue
from app.domain.decision_packet import DecisionPacketBuilder
from app.domain.market_depth import MarketDepthEngine
from app.domain.operator import OperatorControlEngine

def test_full_pipeline_e2e_execution():
    # 1. Ingestion Queue Dequeue
    queue = EventIngestionQueue(max_capacity=10)
    queue.enqueue("EVT-WX-ORD-01", {"event_id": "EVT-WX-ORD-01", "raw_prob": 0.78, "yes_ask": 0.50}, priority=1)
    item = queue.dequeue()
    assert item is not None
    payload = item["payload"]

    # 2. Decision Packet Generation & Kelly Allocation
    builder = DecisionPacketBuilder(kelly_fraction=0.25, max_position_pct=0.10)
    packet = builder.build_decision_packet(
        event_id=payload["event_id"],
        raw_prob=payload["raw_prob"],
        yes_ask=payload["yes_ask"],
        total_capital=100000.0,
        reliability_factor=1.0
    )
    assert packet["operating_mode"] == "NORMAL"
    stake = packet["capital_bid"]["recommended_stake"]
    assert stake > 0

    # 3. Market Depth & Slippage Evaluation
    depth_engine = MarketDepthEngine(fee_rate=0.01)
    order_book = [
        {"price": 0.50, "size": 5000.0},
        {"price": 0.52, "size": 10000.0}
    ]
    depth_result = depth_engine.evaluate_order_depth(order_book, requested_volume=stake)
    assert depth_result["executable"] is True
    assert depth_result["executed_volume"] == stake
    assert depth_result["vwap"] >= 0.50

    # 4. Operator Session Execution & Audit Logging
    operator = OperatorControlEngine()
    session = operator.start_paper_session("tenant_prime", initial_capital=100000.0)
    session_id = session["session_id"]
    
    session["current_balance"] -= stake
    operator.log_audit_event("tenant_prime", "ORDER_EXECUTED", {
        "session_id": session_id,
        "event_id": payload["event_id"],
        "stake": stake,
        "vwap": depth_result["vwap"],
        "slippage": depth_result["slippage"]
    })

    assert session["current_balance"] == 100000.0 - stake
    assert len(operator.audit_log) == 2
    assert operator.audit_log[1]["action"] == "ORDER_EXECUTED"
