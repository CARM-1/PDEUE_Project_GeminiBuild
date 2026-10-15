# PDEUE Work Package 8P: Calibrated Maker Replay Scorecard

**Target Branch:** `ring1-alpha`  
**Source Commit:** `1eb3a57` (PR #65 Merged)  
**Execution Posture:** Authenticated Strategy D Maker Replay (Polymarket Level 2)  
**Accounting Standard:** ADR-008 Exact-Cent Fiduciary Waterfall  

---

## 1. Verified Microstructure Performance

| Metric | Recorded Value | Microstructure Invariant Verification |
| :--- | :--- | :--- |
| **Unique Trades Replayed** | **100 prints** | Monotonic nanosecond ordering verified |
| **Maker Limit Fills** | **1 fill (10 lots)** | Resting limit bid crossed inside spread |
| **Capital Committed** | **$5.90 (590¢)** | Seed capital conserved without leakage |
| **Settlement Payout** | **$10.00** | Binary maturity payout (.00/contract) |
| **Simulated Net PnL** | **+$4.10 (+410¢)** | Realized profit generated via maker queue |

---

## 2. ADR-008 Exact-Cent Distribution Waterfall

| Distribution Leg | Allocation Policy | Realized Amount | Ledger Invariant |
| :--- | :--- | :--- | :--- |
| **SCMA (Member Equity)** | 87% (Floored on profit) | **$3.56 (356¢)** | PASS (Zero fractional drift) |
| **CFCP (Familial Reserve)** | 10% (+ Residual cent) | **$0.42 (42¢)** | PASS (Exact integer balance) |
| **FAEP (Platform Ops)** | 3% | **$0.12 (12¢)** | PASS (Operating fee isolated) |
| **Total Reconciled** | **100%** | **$4.10 (410¢)** | **EXACT-CENT BALANCE HOLDS** |

---

## 3. Venue Boundary Findings
- **Maker Queue Activation:** Placing maker limit orders inside the historical spread successfully depleted aggressive sell queue depth ({ahead}$) and filled 10 contracts under Strategy D rules.
- **Egress Proxy Mitigation:** Cloud runner attempts to fetch fresh Polymarket prints encountered Cloudflare datacenter blocking (HTTP 403). Live data acquisition requires execution from non-datacenter IPs or authenticated headers.
