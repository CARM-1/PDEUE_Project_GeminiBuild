# ADR-012: High-Water Mark (HWM) per SCMA Profit Waterfall Policy

- **Status:** Ratified (November 22, 2026)
- **Authority:** Founder / Chief Administrator (Project FUTURE Governance)
- **Supersedes:** Implicit per-trade 87/10/3 waterfall triggers during drawdowns
- **Resolves:** Gate G2 Independent Umpire Binding Modification `B9`

## Decision
The canonical **87% SCMA / 10% CFCP / 3% FAEP** profit waterfall executes strictly on **net new profit above each SCMA's prior High-Water Mark (HWM)**, rather than on every isolated winning trade.

## Exact Integer-Cent Mechanics (ADR-008 Compliant)
Let $E_{\text{before}}$ be the SCMA's pre-settlement equity, $H_{\text{before}}$ be its prior High-Water Mark ($H_{\text{before}} \ge E_{\text{before}}$), and $P = \text{net\_pnl\_cents}$:
1. **Losing or Flat Settlement ($P \le 0$):**
   - `hwm_eligible_profit_cents = 0`
   - `scma_allocation_cents = P`, `cfcp_allocation_cents = 0`, `faep_allocation_cents = 0`, `residual_cents = 0`
   - $H_{\text{after}} = H_{\text{before}}$
2. **Winning Settlement ($P > 0$):**
   - Deficit to HWM: $D = \max(0, H_{\text{before}} - E_{\text{before}})$
   - Recovery portion (100% retained in SCMA): $P_{\text{rec}} = \min(P, D)$
   - HWM-eligible new profit: $P_{\text{hwm}} = P - P_{\text{rec}}$
   - If $P_{\text{hwm}} == 0$: `scma_allocation_cents = P`, `cfcp = 0`, `faep = 0`, `residual = 0`, $H_{\text{after}} = H_{\text{before}}$.
   - If $P_{\text{hwm}} > 0$:
     - `scma_hwm = (P_hwm * 87) // 100`
     - `faep = (P_hwm * 3) // 100`
     - `cfcp = P_hwm - scma_hwm - faep` (includes `residual_cents = cfcp - (P_hwm * 10) // 100` in `{0, 1, 2}`)
     - `scma_allocation_cents = P_rec + scma_hwm`
     - $H_{\text{after}} = E_{\text{before}} + \text{scma\_allocation\_cents}$

## Governance Rationale
Per-trade splitting imposes a hidden 13% "volatility tax" during choppy, flat periods—shrinking a member's balance while communal pools grow. In a macro regime of elevated geopolitical shocks, inflation, and cyber fragility, High-Water Mark accounting protects the ignition sprint to the $25,000 on-venue float cap, preserves family solidarity (*Concordia*), and guarantees that every dollar swept into the Delaware Dynasty Trust (CFCP) represents genuine, unencumbered net wealth.
