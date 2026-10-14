# PDEUE Work Package 8N: Authentic Polymarket Replay Scorecard

**Target Branch:** `ring1-alpha`  
**Source Artifact:** `backend/reports/authentic_batch_replay_scorecard.json`  
**Execution Mode:** Batch Walk-Forward Engine (Authentic Polymarket L2 Data)  
**Accounting Standard:** ADR-008 Integer-Cent Ledger Conservation  

---

## 1. Executive Performance Summary

| Metric | Recorded Value | Microstructure Invariant Verification |
| :--- | :--- | :--- |
| **Total Market Tapes Ingested** | **30** | 30 raw JSON captures parsed from `data/venues/polymarket/` |
| **Total Level 2 Prints Parsed** | **3,000** | 100 prints per file across all 30 captures |
| **Filtered Target Contract Prints** | **630** | Filtered to primary contract (`0x64cb...`) without cross-book collision |
| **Fiduciary Underwriting Admissions**| **30** | Valid zero-lookahead point-in-time scenarios admitted |
| **Fiduciary Underwriting Abstentions**| **0** | Zero unhedged orders placed without pre-trade inputs |
| **Maker Limit Fills Executed** | **0** | Strategy D resting limit orders ({ahead}$ priority preserved) |
| **Total Capital Deployed** | **$0.00** | Seed capital conserved (00.00 intact) |
| **Simulated Net Realized PnL** | **$0.00** | Exact-cent ledger tracking |

---

## 2. ADR-008 Exact-Cent Fiduciary Waterfall

| Distribution Leg | Target Allocation | Split Amount | Ledger Verification |
| :--- | :--- | :--- | :--- |
| **SCMA (Member Equity)** | 87% (Floored on gain, absorbs 100% loss) | $0.00 | PASS (Exact-cent allocation) |
| **CFCP (Family Shield Reserve)** | 10% (+ Residual integer cent) | $0.00 | PASS (Zero fractional leakage) |
| **FAEP (Platform Operations)** | 3% | $0.00 | PASS (Exact integer calculation) |
| **Total Reconciled Waterfall** | **100%** | **$0.00** | **MATCHES NET PNL EXACTLY** |

---

## 3. Disclosed Tape Ingestion Findings
1. **Corpus Duplication Identified:** All 30 harvested files contain the identical 100-trade execution snapshot. The underlying harvester script polled the Polymarket endpoint without a rolling timestamp cursor.
2. **Resting Maker Dynamics:** Maker limit orders were underwritten with valid pre-tape timestamps, but aggressive sell flow did not cross into our resting limit bid depth ({ahead}$), resulting in zero maker fills and zero capital risk.
3. **Purity Gate Clearance:** The multi-contract collision at line 154 is eliminated; only prints belonging to the underwritten contract were ingested into the harness.
