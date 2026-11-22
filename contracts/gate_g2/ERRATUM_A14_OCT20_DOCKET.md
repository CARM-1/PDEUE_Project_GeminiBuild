# Erratum: Rule A14 Loss Isolation Correction (Oct 20, 2026 Docket)

- **Document ID:** `ERRATUM-G2-A14-20261122`
- **Governing Authority:** Founder / Chief Administrator Ratification & Independent Gate G2 Umpire Ruling (B5)
- **Affected Historical Record:** October 20, 2026 Session Initialization & Resumption Docket

## Correction
The October 20, 2026 docket summary erroneously stated: *"Losses absorbed 100% by CFCP reserves."*

That line is formally rescinded as a documentation error. The binding architectural, mathematical, and fiduciary rule across PDEUE (`Rule A14`) is:
1. **100% SCMA Loss Isolation:** Every trading loss (`net_pnl_cents < 0`) is absorbed 100% by the executing Self-Contained Member Account (`scma_allocation_cents == net_pnl_cents`).
2. **Zero Communal Loss Absorption:** Neither the Central Familial Common Pool (`CFCP`) nor the Founder/Admin Endowment Pool (`FAEP`) ever absorbs trading drawdowns (`cfcp_allocation_cents == 0`, `faep_allocation_cents == 0`, `residual_cents == 0`).
3. **Waterfall Hard Guard:** The 87/10/3 profit waterfall function is strictly prohibited from executing when `net_pnl_cents <= 0` or `hwm_eligible_profit_cents <= 0` (preventing negative floor-division sign leaks).
