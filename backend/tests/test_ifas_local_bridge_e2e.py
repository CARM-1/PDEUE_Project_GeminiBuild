"""Play #12B hermetic E2E tests for PDEUE accounting_router <-> ifas_local_bridge alignment."""
import csv
import sys
from pathlib import Path
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import ifas_local_bridge  # noqa: E402
from app.main import app  # noqa: E402
from app.api.v1.accounting_router import global_accounting_gateway  # noqa: E402


def _snapshot_gateway():
    return (
        list(global_accounting_gateway.event_outbox),
        dict(global_accounting_gateway.reconciliation_receipts),
        global_accounting_gateway._seq_counter,
    )


def _restore_gateway(snap):
    global_accounting_gateway.event_outbox[:] = snap[0]
    global_accounting_gateway.reconciliation_receipts.clear()
    global_accounting_gateway.reconciliation_receipts.update(snap[1])
    global_accounting_gateway._seq_counter = snap[2]


def test_ifas_bridge_syncs_acknowledges_and_exports_exact_cents_e2e(tmp_path):
    snap = _snapshot_gateway()
    try:
        global_accounting_gateway.event_outbox.clear()
        global_accounting_gateway.reconciliation_receipts.clear()
        global_accounting_gateway._seq_counter = 0

        global_accounting_gateway.emit_settlement_event(
            contract_id="KXHIGHMIA-26NOV22-T80",
            scma_id="SCMA-MEM-0001",
            gross_payout_cents=1000,
            scma_net_cents=870,
            cfcp_cents=100,
            faep_cents=30,
        )
        client = TestClient(app)
        ledger_p = tmp_path / "ledger.json"
        csv_p = tmp_path / "export.csv"
        stmt_p = tmp_path / "stmt.txt"

        res = ifas_local_bridge.run_sync(
            node_url="",
            ledger_path=ledger_p,
            csv_path=csv_p,
            statement_path=stmt_p,
            http_client=client,
        )
        assert res["ingested"] == 1
        assert res["rejected"] == 0
        assert res["totals_cents"] == {
            "gross_payout": 1000,
            "scma_net": 870,
            "cfcp_allocation": 100,
            "faep_allocation": 30,
        }
        assert global_accounting_gateway.event_outbox[0]["status"] == "RECONCILED"

        # Second sync is strictly idempotent (zero duplicate ingestion)
        res2 = ifas_local_bridge.run_sync(
            node_url="", ledger_path=ledger_p, csv_path=csv_p, statement_path=stmt_p, http_client=client
        )
        assert res2["ingested"] == 0
        assert res2["totals_cents"]["gross_payout"] == 1000

        with csv_p.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 1
        assert int(rows[0]["scma_net_cents"]) == 870
        assert int(rows[0]["cfcp_allocation_cents"]) == 100
        assert int(rows[0]["faep_allocation_cents"]) == 30
    finally:
        _restore_gateway(snap)


def test_ifas_bridge_rejects_tampered_signature_and_leaves_unreconciled(tmp_path):
    snap = _snapshot_gateway()
    try:
        global_accounting_gateway.event_outbox.clear()
        global_accounting_gateway.reconciliation_receipts.clear()
        global_accounting_gateway._seq_counter = 0

        env = global_accounting_gateway.emit_settlement_event(
            contract_id="KX-TAMPER", scma_id="SCMA-FOUNDER",
            gross_payout_cents=500, scma_net_cents=435, cfcp_cents=50, faep_cents=15,
        )
        env["signature_hmac_sha256"] = "0" * 64  # tamper signature

        client = TestClient(app)
        res = ifas_local_bridge.run_sync(
            node_url="",
            ledger_path=tmp_path / "l.json",
            csv_path=tmp_path / "e.csv",
            statement_path=tmp_path / "s.txt",
            http_client=client,
        )
        assert res["ingested"] == 0
        assert res["rejected"] == 1
        assert global_accounting_gateway.event_outbox[0]["status"] == "EMITTED"
    finally:
        _restore_gateway(snap)
