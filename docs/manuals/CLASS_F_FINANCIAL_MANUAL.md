# Class F Financial and Lineal Fiduciary Manual

**Audience:** F1 Peer Guide, F2-H Head of Household, F2-A Lineage Advisor, and F3 Chief Risk Officer
**Workspace:** `/advisor?role=F1`, `F2-H`, `F2-A`, or `F3`
**Mission:** provide least-privilege guidance, domestic protection, advisory review, and platform risk supervision

## 1. Active hats and common rules

Open `/advisor` through the approved identity flow and verify the active hat before reading or acting. The role switcher demonstrates each workspace contract; it is not evidence that the signed-in user owns every claim. Server authorization is authoritative. Use the least privileged hat that can complete the task, and never share a session.

All roles distinguish unavailable from zero, unrealized from realized, proposal from approval, and visibility from authority. Monetary state follows **ADR-008, Exact-Cent Conservation**: authoritative values are integer cents and split components must exactly equal their source. Accounting integration follows **ADR-011, Signed Accounting Outbox and Custodial Boundary**: signed, sequenced events pass to approved accounting without storing bank credentials. Neither rule can be waived by an advisory decision.

**Directive R-12 Financial Masking** applies to the technical telemetry plane: engineers ordinarily receive immutable redactions of tenant balances, while an approved T3 diagnostic can obtain only a temporary CA-authorized unmask grant. Class F users must not disclose financial values to help an engineer circumvent that control. Use correlation identifiers and the governed escalation path instead.

## 2. F1 Peer Guide

F1 supports a restricted mentee view. The Peer Guide can explain terms, help interpret risk education, and identify an escalation route for the assigned mentee. F1 sees neither full household equity nor general distribution queues. Redaction is a boundary, not a UI inconvenience.

F1 must not co-sign spending, stage lineage-wide changes, adjudicate proposals, inspect other members, infer redacted totals, or represent educational discussion as financial advice. Record the topic and referral without copying private balances. Escalate account changes to F2-H and broader advisory questions to F2-A.

## 3. F2-H Head of Household

F2-H operates the domestic household view: household roster, independent and custodial accounts, available liquidity, pending domestic distributions, and point-in-time explanations. Confirm household scope and request identity before acting.

### Head of Household Protection Rule

**F2-H alone holds co-signature authority over domestic spending.** The rule places the decision with the role accountable for household welfare and familiar with current domestic obligations. F2-A can recommend but cannot spend; F3 can supervise platform risk but cannot substitute its macro mandate for household consent. Both remain read-only auditors for the domestic co-sign queue.

For a co-signature, verify beneficiary, category, amount, purpose, source account, custodial status, supporting evidence, duplicate state, and effect on protected liquidity. Read the confirmation and sign once. A co-signature does not bypass a second required control, a legal restriction, a capital floor, or an active halt. Deny or defer ambiguous requests and preserve the reason.

Never let F2-A or F3 “help” by using the F2-H session. A `403` for those roles is the expected protection. If controls appear enabled for an unauthorized role, stop and report a security defect rather than testing with real data.

## 4. F2-A Lineage Advisor

F2-A sees advisory context across the permitted branch, selects the intended household or SCMA, reviews policy and evidence, and stages changes for supervision. F2-A does not directly mutate risk or co-sign domestic spending.

Before a proposal, confirm current dial, certified ceiling, household context, concentration, liquidity, settlement state, and justification. The proposed value must remain within governance constraints. Use precise language and state expected benefit, risks, evidence, duration, and review condition. Submit once and preserve the proposal identifier.

The result is **PENDING**. Pending means no approved change has occurred. F2-A cannot adjudicate its own proposal, and should not promise the member that it will be accepted. A changed target, amount, or rationale requires a new proposal rather than editing around prior review.

## 5. F3 Chief Risk Officer

F3 operates the macro-risk desk: global 99% VaR, cross-House gross margin and utilization, 12-House exposure rollups, venue distribution, concentration status, Directive R-04 state, and the supervisory proposal queue. F3's view is broad because the mandate is platform risk, not household spending.

F3 reviews evidence, determines whether a pending advisory change fits platform policy, and records **ALLOWED** or **DENIED**. F3 remains read-only for domestic distributions. An allowed proposal indicates supervisory admission; it does not itself claim that every later execution or co-signature completed. Denial is a durable risk decision, not an error to bypass.

F3 may recommend **Directive R-04 Emergency Financial Halt** when aggregate risk, ledger uncertainty, venue distress, or control failure threatens capital. R-04 stops financial commitments and must be distinguished from a technical service halt. F3 cannot use technical controls or clear a halt outside the governed authorization path.

## 6. Tri-State Advisory Proposal Pipeline

The canonical state machine is **PENDING → ALLOWED** or **PENDING → DENIED**. There is no implicit approval, and a terminal decision must not be silently reversed.

### Stage as F2-A

1. Choose the correct branch, household, and target SCMA.
2. Verify the current state and freshness.
3. Enter the proposed risk dial or advisory change within certified bounds.
4. Write a fiduciary justification linking evidence, benefit, downside, and review plan.
5. Review the complete payload and submit once.
6. Confirm a proposal identifier, submitter, timestamp, and `PENDING` state.

Staging is intentionally nonexecuting. It creates an immutable review artifact. F2-A should monitor the queue but cannot use the adjudication endpoint.

### Adjudicate as F3

1. Confirm the item is still `PENDING` and unexpired.
2. Validate target, sponsor, current and proposed values, evidence freshness, certified ceiling, household and platform concentration, liquidity, venue exposure, and R-04 status.
3. Check conflicts and whether another pending proposal overlaps.
4. Choose `ALLOW` only when every policy gate and justification is satisfied; otherwise choose `DENY` and record the reason.
5. Confirm the terminal state, adjudicator, UTC time, and audit record.

An API or UI may preserve a legacy label for a seeded item, but operators should reason using the canonical tri-state lifecycle. Do not re-submit a denied proposal unchanged to shop for approval. Materially new evidence belongs in a new linked proposal.

## 7. Platform 99% Value at Risk

The **99% VaR** gauge estimates a loss threshold over its stated horizon, commonly 24 hours, under the model and data assumptions. It does not say the maximum possible loss; outcomes worse than VaR remain possible. Read the value with timestamp, horizon, confidence, method version, data completeness, and current exposure.

Do not compare a stale VaR with current positions or treat a lower number as proof of safety. Review stress tests, liquidity, correlated factors, unsettled positions, and model limitations. A value displayed beside a fixed comparison should be interpreted in its documented units; never mix dollars and cents. Investigate sudden drops as carefully as sudden increases because missing positions can falsely improve a metric.

F3 should define escalation bands and record breaches. At a warning band, investigate drivers and restrict new concentration. At a limit breach, fail closed according to policy and consider R-04. F2-A uses aggregate signals to shape proposals but cannot override the CRO conclusion. F2-H may see relevant domestic impact without receiving platform adjudication power.

## 8. Twelve-House exposure rollups

The 12-House table aggregates exposure and margin utilization for each House. Use it to find concentration, correlated lineage risk, and unequal utilization. Validate that all Houses are present exactly once, the as-of time matches the platform summary, and totals reconcile to their defined population. A missing House is an incomplete rollup, not zero exposure.

Review gross and net views where supplied. Netting can conceal offsetting positions that still carry venue, liquidity, basis, or settlement risk. Look at utilization relative to governed capacity and investigate rapid changes. Drill-down must respect household privacy; F3 needs risk evidence, not unrelated domestic detail.

House voting and financial supervision are distinct. A House majority does not approve a risk breach or execute a disbursement. Lineage petitions that meet the nine-of-twelve threshold remain pending Sovereign Settlor adjudication and required dual control.

## 9. Exchange counterparty concentration

Venue distribution compares exposure across approved counterparties such as Kalshi and Polymarket. Concentration risk includes collateral trapped at a venue, outage or settlement delay, legal or operational change, correlated order failures, and inability to rebalance. Percentages must state whether they measure gross exposure, collateral, margin, or another denominator.

F3 reviews total and per-venue amount, trend, liquidity, unsettled items, error rates, and collateral balance. A visually balanced percentage is not automatically safe if both venues share a factor or one is impaired. The system's rebalance signals and concentration caps are policy inputs; do not evade them by splitting economically identical positions.

When a venue degrades, constrain new admission, reconcile open orders, identify stranded collateral, coordinate technical diagnosis, and consider R-04 if capital truth is uncertain. Technical staff manage adapters and rate limits—Kalshi and Polymarket are independently limited to 10 requests per second—but do not make the financial concentration decision.

## 10. Domestic spending versus advisory and macro authority

Three workflows are deliberately separate:

* A domestic distribution is co-signed by F2-H after household review.
* A lineage advisory change is staged by F2-A and adjudicated by F3.
* A platform emergency is handled under R-04 and higher governance.

No role may combine these simply because one person holds multiple appointments. Select the active hat, complete its step, end that context, and obtain genuinely independent review where required. F3's broad metrics do not grant domestic consent. F2-H's domestic consent does not grant platform risk authority. F2-A's expertise does not make its own proposal approved.

## 11. Waterfall, pools, and custodial boundaries

Eligible realized proceeds follow the deterministic 87/10/3 waterfall: 87% to private SCMA compounding, 10% to the CFCP safety shield, and 3% to FAEP endowment. Apply the split only to eligible settled net proceeds. Open profit, an estimate, or a pending venue result is not distributable.

CFCP is a protected resilience pool, not ordinary household liquidity. FAEP is long-horizon lineal capital, not discretionary spending. Visibility in `/advisor` creates no withdrawal right. The FBO custodial architecture also limits on-venue float to $25,000; excess is handled through an ADR-011 signed sweep workflow.

If a split does not conserve exact cents, stop and reconcile under ADR-008. If an outbox event is duplicated or unsigned, quarantine it and replay by idempotency identity after technical correction. Never “fix” either problem with an informal transfer.

## 12. Directive R-04 response for Class F

Indicators include VaR or concentration breach, unexplained balance variance, corrupted proposal state, compromised financial identity, venue uncertainty with material exposure, or failure of a mandatory gate. Preserve evidence, stop new financial commitments, notify the Chief Administrator, and identify affected Houses and venues without oversharing.

During R-04, continue safe read-only reconciliation and incident coordination. Do not approve proposals, co-sign spending, or ask engineers to restart around the halt. Recovery requires reconciled positions, verified ledgers and outbox, resolved control failure, required dual authorization, and monitored staged restoration.

## 13. Routine reviews

F1 reviews assigned mentee education and referrals. F2-H reviews pending distributions, protected liquidity, custodial accounts, and anomalies. F2-A reviews branch exposure, pending proposals, and changes in evidence. F3 reviews VaR, House rollups, venue concentration, margin utilization, proposal aging, R-04 status, and reconciliation exceptions.

At handoff, state the active role, as-of time, unresolved domestic requests, pending and terminal proposals, risk breaches, stale inputs, concentration concerns, halt state, and accountable next owner. Do not include secrets, unnecessary household detail, or reconstructed redactions.

## 14. Common failure modes

Do not infer zero from missing data, approve a proposal you staged, let F3 co-sign domestic spending, let F2-H decide platform VaR policy, treat VaR as a worst case, net away gross counterparty exposure, distribute unrealized gains, bypass a certified risk ceiling, duplicate an outbox event, or clear R-04 because services look healthy.

If the interface offers a capability contrary to this manual, the restrictive rule wins. Stop, preserve sanitized evidence, and report the authorization defect.

## 15. Fiduciary attestation

Before a material decision, be able to say: the correct hat is active; scope and identity are verified; data is current; money is integer cents; proposal and execution are distinguished; domestic co-signature remains F2-H-only; F2-A staging remains nonexecuting; F3 adjudication is independent; VaR, House, and venue concentration were reviewed; R-04 is respected; and ADR-008 and ADR-011 evidence can be audited.

Class F is a system of checks rather than a hierarchy of convenience. Peer education, household protection, lineage advice, and macro-risk supervision remain separate so that no attractive recommendation or urgent request can silently become uncontrolled financial action.
