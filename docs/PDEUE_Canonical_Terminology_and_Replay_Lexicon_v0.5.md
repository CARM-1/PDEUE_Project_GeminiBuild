# PDEUE Canonical Terminology and Replay Lexicon v0.5

**Project:** PDEUE — Public Data Event Underwriting Engine  
**Governance family:** Project FUTURE Financial Generation System (FGS)  
**Status:** **OFFICIALLY RATIFIED AND BINDING**  
**Effective version:** v0.5  
**Supersession:** This standard supersedes v0.4 in full. References to the “canonical lexicon” without a version mean this version until a later version is ratified.

This document fixes the vocabulary used in requirements, architecture decisions, interfaces, user interfaces, replay reports, tests, audit evidence, incident records, and approvals. “MUST,” “MUST NOT,” “SHALL,” and “SHALL NOT” are binding. “Should” expresses a preferred practice. A friendly label may accompany a canonical term in a member-facing view, but it must not silently change the underlying meaning.

## 1. Scope, interpretation, and binding language

### 1.1 System names

**Public Data Event Underwriting Engine (PDEUE).** A governed Financial Generation Engine that converts lawful public information and point-in-time venue state into evidence, calibrated probability and uncertainty, candidate selection, risk-bounded decisions, execution intents, settlement events, and reproducible replay evidence. PDEUE is not the external bank, the independent accounting authority, or a guarantee of profit.

**Financial Generation System (FGS).** The common identity, authorization, policy, audit, deployment, and record-exchange control plane under which one or more Financial Generation Engines operate.

**Financial Generation Engine (FGE).** A software-based revenue or capital-generation engine governed by the FGS. PDEUE is an FGE. An engine may recommend or stage an action only within its assigned authority.

**Multigenerational Legacy Financial Generation Engine.** The long-horizon purpose of PDEUE: preserve, govern, and compound capital for multiple lineal generations while maintaining tenant isolation, evidence provenance, conservative risk limits, and human accountability.

### 1.2 Words that must be qualified

The bare word **market** is ambiguous and MUST be replaced where scope matters by **market archetype**, **market family**, **market category/domain**, **venue**, **venue-listed contract**, **instrument**, **candidate universe**, **historical case**, **historical anchor trade/fill**, **replay decision**, or **replay trade**.

The bare word **trade** MUST be qualified as **historical venue trade/fill**, **historical anchor trade/fill**, **replay trade**, **paper trade**, or **live trade**. A replay trade is a counterfactual system output; it is never evidence that an external order existed.

The bare words **administrator** and **advisor** MUST be qualified. Use **Chief Administrator**, **System Administrator Tier 1/2/3 (T1/T2/T3)**, or **Financial Advisor Tier 1/2/3 (F1/F2/F3)**. When the F2 scope matters, use **F2-H** or **F2-A**.

**Point-in-time (PIT).** The state knowable at or before a declared UTC cutoff. Evidence published after the cutoff is inadmissible even if later shown to be accurate. “As of” always identifies a cutoff, not a retrieval time.

**Fail closed.** Refuse mutation, dispatch, settlement release, or disclosure when required identity, evidence, freshness, authorization, reconciliation, or conservation proof is absent. A failed control does not become permission through timeout or retry.

## 2. Capital pools, ownership, and deterministic flows

**Self-Contained Member Account (SCMA).** A tenant-partitioned member ledger containing discrete seed principal, integer-cent available cash, reservations, inventory, realized results, and a downward-only risk profile. One SCMA MUST NOT cross-collateralize, satisfy the loss of, or leak records from another SCMA. “Member balance” means a balance inside one named SCMA, not family-wide assets.

**Central Familial Common Pool (CFCP).** A non-trading treasury sub-ledger that receives the canonical ten-percent share of eligible realized positive proceeds. The CFCP is a familial reserve and capital-floor shield. It is not spare member buying power and is not owned by a technical operator.

**Founder/Chief Administrator Endowment Pool (FAEP).** A dedicated administrative/endowment treasury sub-ledger receiving the canonical three-percent share of eligible realized positive proceeds. FAEP is the full canonical name; “founder pool” may appear only as a clearly mapped legacy database label.

**Familial Stability Advance Pool (FSAP).** A governed stability facility that can fund an approved advance for a recipient SCMA and direct creditor payments. Registration requires dual control by the F2 Head of Household and Chief Administrator, a cent-conserving disbursement plan, and a defined dividend-sweep interception ratio. The ratio remains within the approved 30–70 percent band, changes are time-locked, amortization never exceeds the outstanding advance, and every registration or amortization is emitted across the accounting boundary. FSAP is assistance subject to repayment rules; it is neither a gift label nor trading collateral by implication.

**Transaction Profit Waterfall (TPW), or 87/10/3 waterfall.** The deterministic allocation of eligible realized positive proceeds: 87% to the executing SCMA, 10% to CFCP, and 3% to FAEP. Integer division is applied under ADR-008; any remainder necessary for exact conservation is assigned according to the approved settlement rule, canonically the CFCP. Losses remain entirely within the executing SCMA. Percentages apply to the defined eligible amount, never to a casually selected balance. Interfaces MUST disclose whether the basis is gross payout, realized gain, yield, or rebate.

**Reservation.** Integer cents made unavailable before dispatch to prevent double commitment. Reservation is not a fill, expense, or realized loss. Release and consumption must be idempotent and traceable to the same intent.

**Dry powder.** Uncommitted, spendable capital after existing reservations and proposed commitments. The **40% floor** means a dispatch batch MUST leave at least forty percent of applicable pre-dispatch total equity uncommitted. The floor is computed with integer arithmetic and rounded conservatively upward; priority eviction may remove weaker intents rather than breach it.

## 3. Roles, hats, authority, and directives R-01 through R-06

**Chief Administrator (CA).** Highest human administrative and governance role. The CA appoints privileged roles, approves material production policy, and participates in prescribed dual controls, but remains bounded by immutable risk ceilings, SCMA isolation, exact-cent conservation, and audit requirements.

**System Administrators.** **T1** performs bounded diagnostics; **T2** manages approved operational services; **T3** manages production infrastructure, secrets, and releases. Technical authority does not confer financial authority. Material financial-logic deployment requires the specified independent approvals.

**Financial Advisors.** **F1** provides member-scoped education and guidance. **F2-H (Head of Household)** acts within one household and performs specifically assigned household governance. **F2-A (Lineage Advisor)** may oversee explicitly delegated household branches without acquiring ownership of their SCMAs. **F3** supervises platform-wide risk, strategy promotion, and financial emergency controls. Advice is not execution authority.

**Member User.** An authenticated family member acting only within their own SCMA. A member may lower their permitted risk dial, view authorized education and evidence, and submit permitted requests; a member cannot raise immutable ceilings or inspect another tenant.

**Active Hat.** The one role context selected for an action. **Split-Hat Enforcement** prevents a multi-role person from combining technical, financial, administrative, and member privileges in one action. Changing hats creates a new authorization context and audit event; it does not retroactively authorize an earlier action.

**AUTH-01 — Non-Unilateral Financial Execution.** Financial commitment, emergency action, or other consequential action designated by policy requires the proper human authorization/quorum. An AI assistant may explain, calculate, or stage an action card but cannot self-approve it.

**Directive R-01 — Named Identity and Tenant Boundary.** Every consequential request is attributable to an authenticated actor, active hat, tenant, and target resource. Anonymous or inferred authority is invalid.

**Directive R-02 — Least Authority by Role.** Permissions are allow-listed to the narrowest role and scope. Role seniority does not automatically aggregate permissions from other classes.

**Directive R-03 — Dual Control for Material Mutation.** Designated releases, pool movements, authority changes, and financial actions require independently authenticated qualified approvers. The proposer cannot impersonate the approver.

**Directive R-04 — Emergency Financial Halt.** R-04 stops new financial commitments and any unsafe settlement or disbursement release when capital, ledger integrity, venue truth, or financial authority is in doubt. It is distinct from stopping a worker or web service. Activation and clearance require recorded actor, UTC time, reason, scope, evidence, and governed authorization. Read-only evidence should remain available where safe.

**Directive R-05 — Downward-Only Member Risk.** A member control may reduce risk below the authorized ceiling but MUST NOT raise the ceiling. A request above the bound fails closed or enters a separately governed proposal workflow; it never mutates directly.

**Directive R-06 — Split-Hat Role Mapping.** Portals, endpoints, and audit records expose and enforce the selected Active Hat. Member, advisory, technical, and CA powers cannot be blended merely because one natural person holds multiple appointments.

## 4. Governance directives R-07 through R-13

**Directive R-07 — SCMA Isolation and Loss Containment.** Capital, reservations, inventory, losses, statements, and policy settings remain tenant-partitioned. Cross-account aggregation may be shown only to an authorized advisory or risk role and never creates cross-collateralization.

**Directive R-08 — Deterministic Waterfall and Conservation.** Every eligible positive settlement, rebate, or yield event identifies its basis and produces an exact, reproducible 87/10/3 allocation. The component cents MUST equal the input cents and duplicate processing MUST NOT allocate twice.

**Directive R-09 — Immutable Risk Envelope.** Engine ceilings outrank member preferences, strategy suggestions, and operator convenience. Position, correlated-factor, liquidity, concentration, and dry-powder limits are evaluated before commitment; unknown inputs cause rejection.

**Directive R-10 — Point-in-Time Evidence Integrity.** Underwriting and replay use only evidence available by the declared cutoff, preserve publication and observation times, and identify source and transformation lineage. Later corrections may be a separate replay scenario but cannot rewrite the original decision context.

**Directive R-11 — Reproducible Decision and Execution Lineage.** Each decision links evidence snapshot, feature/model/policy versions, probability, uncertainty, price, sizing, approvals, intent, venue response, fills, reconciliation, and settlement. A display summary is not a substitute for the lineage record.

**Directive R-12 — Least-Privilege Financial Masking.** Routine technical telemetry redacts tenant balances, exposure, and sensitive financial values server-side. T1 and T2 cannot unmask. An approved T3 diagnostic may receive only a temporary, page-scoped CA-authorized grant with recorded purpose, expiry, and revocation. Masking is an authorization boundary, not CSS decoration.

**Directive R-13 — Secret and Credential Separation.** Raw external banking credentials are prohibited in PDEUE events, logs, and ledgers. Venue secrets use bounded leases and approved brokers. Interfaces transmit opaque references where an external destination must be identified.

## 5. Governance directives R-14 through R-20

**Directive R-14 — Idempotent Intent and Reconciliation.** Every financial intent has a stable idempotency key. Retries return or reconcile the existing result rather than create another commitment. Internal state, venue state, and independent accounting acknowledgement remain explicitly distinct until reconciled.

**Directive R-15 — Schema-Versioned Interfaces.** Cross-boundary events conform to a named, validated interface and schema. Producers cannot add ambiguous monetary fields, and consumers reject incompatible or malformed events rather than guessing.

**Directive R-16 — Append-Only Audit Evidence.** Material proposals, decisions, approvals, grants, revocations, dispatches, reconciliations, halts, and settlements produce immutable time-ordered evidence. Corrections append a superseding record; they do not erase history.

**Directive R-17 — Strategy Promotion Separation.** Research, replay, paper, and live phases are separate states. Passing historical replay does not grant live authority. Promotion requires declared acceptance criteria, independent review, version pinning, and rollback readiness.

**Directive R-18 — Venue and Microstructure Safety.** Freshness, spread, fees, depth, rate limits, and expected slippage are part of admissibility. If modeled edge disappears after execution costs, or expected slippage exceeds the approved threshold, dispatch fails closed. Venue availability never overrides risk policy.

**Directive R-19 — Settlement Finality and Exception Handling.** A position becomes realized only through authoritative outcome and reconciliation evidence. Disputed, reversed, partial, or stale states remain visibly unresolved and cannot feed the final waterfall as if settled.

**Directive R-20 — Human-Comprehensible Governance.** Member and operator surfaces explain material state, limits, uncertainty, and blocked actions in plain language while retaining canonical identifiers. Visual metaphors support comprehension but never replace amounts, status text, timestamps, or accessible evidence.

Together, R-01 through R-20 are the ratified governance directive set. Implementations may add stricter safeguards, but MUST NOT redefine a directive locally or weaken one through aliases.

## 6. Underwriting, sizing, execution, and settlement invariants

**Candidate universe.** Contracts eligible for evaluation after venue, domain, expiry, data-quality, liquidity, policy, and authorization filters. Inclusion is not an execution recommendation.

**Historical case.** A past event assembled for research. **Historical anchor trade/fill** is an actual recorded venue event used as an observation. **Replay decision** is the engine decision generated using the replay cutoff. **Replay trade** is the simulated execution under declared fill rules. These four terms are never interchangeable.

**Probability and uncertainty.** Probability is the model’s calibrated event likelihood; uncertainty describes limits around that estimate. Probability MUST NOT be presented as certainty or as realized return. The quoted venue price and model probability remain separate fields.

**Edge.** The modeled advantage after using the declared probability and price basis. **Net edge** accounts for spread, fees, slippage, and other approved execution costs. Gross edge cannot justify execution when net edge is non-positive.

**Quarter-Kelly.** The canonical sizing fraction is 0.25 of the applicable full-Kelly result. It is a ceiling input, not a target that must be spent. Final stake is the minimum allowed by Quarter-Kelly, account risk dial, per-trade ceiling, factor/concentration limits, liquidity, available integer cents, and the 40% floor. Negative or indeterminate Kelly values produce no long stake.

**Two-Tier Risk Envelope (B4-RSK).** Tier 1 contains immutable engine ceilings, including the approved per-position and correlated-factor limits and Quarter-Kelly scaling. Tier 2 permits a member or qualified governor to make exposure smaller within scope. No portal, AI recommendation, or operational override may enlarge Tier 1.

**Real-World Microstructure and Slippage Barrier (B4-FIN).** A pre-dispatch control evaluating executable depth, volume-weighted price, spread, fees, and freshness. A liquidity sweep whose expected slippage exceeds 1.5% of entry price, or whose costs eliminate net edge, causes a fail-closed rejection.

**Hybrid Velocity Engine (B7-EXE).** A controlled capital-recycling approach using expiry-horizon filtering and velocity-adjusted ranking. Default behavior holds a binary position to its authoritative maturity outcome. Early harvest is allowed only when an executable resting bid captures at least 80% of maximum profit after exit spread and fees and all other controls pass.

**Order intent.** An authorized, immutable description of contract, side, limit, quantity, maximum cost, SCMA, decision packet, and idempotency key. **Staged** means validated and awaiting the required authorization or routing step. **Routed** means submitted to a venue adapter, not filled. **Fill** means venue-confirmed execution. **Reconciliation** compares the venue report with internal intent and fill records. **Settlement** applies an authoritative outcome and realizes cents.

## 7. Accounting boundary, exact cents, and outbox vocabulary

**ADR-008 — Exact-Cent Conservation.** Every financial state transition uses signed 64-bit integer cents. Floating-point currency is barred from ledger mutation. Inputs are validated against booleans, fractions, negatives where prohibited, and overflow. Allocation, reservation, release, payout, amortization, and waterfall components must conserve their declared total exactly. Presentation may format dollars only after the authoritative cent value is established.

**Independent Financial Accounting and Authoritative-Record System (IFAS).** A physically and logically separate application that independently records and reconciles financial-generation events and external banking records. PDEUE does not become the external bank ledger and does not store raw bank credentials.

**Financial Generation / Accounting Boundary.** The narrow event interface from PDEUE to IFAS. Events are canonicalized, schema-versioned, sequenced, signed, and acknowledged. A reconciliation receipt confirms accounting-system handling; it does not rewrite the originating event.

**ADR-011 — Signed Accounting Outbox.** Financial events are staged in an append-only outbox with unique event ID, monotonic sequence, UTC timestamp, validated payload, cryptographic signature, and delivery status. Delivery is retryable and idempotent. `PENDING` or `EMITTED` is not the same as acknowledged. Banking account numbers, routing numbers, IBANs, SWIFT codes, or credentials are prohibited; opaque destination tokens are used instead.

**IF-038 Dividend Distribution Scheduled.** Versioned event for a governed distribution or high-watermark sweep. **IF-039 Stability Advance Facility Registered** records an FSAP facility and its dual-control evidence. **IF-040 Dividend Sweep Amortization Applied** records the cent-conserving interception and remaining advance. **IF-041 Contributor Incentive Harvested** records an approved incentive harvest. Interface identifiers are stable contract names, not UI labels.

**High-watermark sweep.** A scheduled transfer instruction for settled balance above a defined retained-capital threshold. It is emitted through ADR-011 and is not proof that an external transfer completed.

## 8. Replay, evidence retention, and canonical visual HUD metaphors

**Replay run.** A deterministic evaluation identified by run ID, cutoff, candidate-universe version, evidence manifest, code/model/policy versions, random seed where applicable, venue-state snapshot, fee/slippage model, and output manifest. Re-running those inputs should reproduce the same decisions or surface a documented nondeterminism exception.

**Replay evidence bundle.** The retained set of source identifiers and hashes, admissibility decisions, transformations, features, probability and uncertainty, policy results, sizing calculation, simulated execution assumptions, settlement truth, and metrics. A chart alone is not a bundle. Leakage checks must prove that post-cutoff facts were excluded.

**Counterfactual.** A separately labeled scenario changing one or more assumptions after preserving the original replay. Counterfactual results cannot be mixed into baseline performance. **Paper incubation** is forward observation without live financial commitment; it remains distinct from historical replay and live execution.

**Concentric Asset Engine Rings.** The canonical HUD metaphor for nested governance and capital context. The center represents the current member/SCMA or selected object; successive rings represent governed family pool context, safeguards, and system boundary. Ring area is not an implied balance unless an explicit scale and numeric legend say so. Every ring visualization requires text labels and accessible values.

**Trajectory Curve.** The canonical educational HUD metaphor for progress through governed milestones such as seed capital, first settlement, 40% shield preservation, and high-watermark sweep. It represents state and direction, not a guaranteed growth forecast. Actual and illustrative segments must be visually and textually distinguishable, with UTC cutoff and measurement basis.

**87/10/3 Radar.** The canonical HUD metaphor for recent eligible settlement activity and its SCMA/CFCP/FAEP allocation. The visualization must display the numeric split, allocation basis, settlement status, and labels; color or geometry alone is insufficient. It must not imply that unresolved positions or gross notional have already been distributed.

**Decision packet.** The inspectable record binding evidence, cutoff, probability, uncertainty, price, edge, risk checks, recommended stake, policy versions, and authorization state. The packet explains why an action was proposed; it does not itself prove routing, filling, or settlement.

**Evidence retention.** Canonical identifiers, timestamps, hashes, versions, approvals, and results are retained according to policy so an authorized reviewer can reconstruct the lifecycle. Sensitive values remain subject to R-12 and tenant scope even in replay tooling.

## 9. Adoption, conformance, and change control

Version 0.5 is the officially binding standard for PDEUE source code, architecture records, schemas, manuals, tests, fixtures, portal copy, action cards, replay reports, incidents, releases, and pull requests. It incorporates and ratifies Directives R-01 through R-20; SCMA, CFCP, FAEP, and FSAP; Quarter-Kelly and the 40% floor; ADR-008 and ADR-011; and the Concentric Asset Engine Rings, Trajectory Curve, and 87/10/3 Radar metaphors.

An implementation **conforms** only when its behavior and authoritative data model match these definitions. Textual presence alone is insufficient. Legacy field names may remain temporarily for compatibility if they are explicitly mapped, do not leak into new canonical interfaces, and do not alter meaning. Friendly portal labels must preserve canonical terminology in accessible detail, API contracts, or accompanying explanations.

When two documents conflict, this v0.5 lexicon controls terminology. A ratified architecture decision may specify implementation mechanics but may not silently redefine these terms. Safety constraints compose by choosing the stricter result. Uncertainty about authority, accounting conservation, evidence cutoff, tenant scope, or settlement status must fail closed and be escalated through the applicable governance path.

Changes require a new version, review of affected interfaces and retention tests, a written migration note, and formal ratification. Editors must not modify the meaning of v0.5 in place after ratification; corrections are made by a superseding version. Historical artifacts retain the version under which they were produced.

**Canonical adoption statement:** PDEUE Canonical Terminology and Replay Lexicon v0.5 is hereby ratified, is officially binding, and supersedes PDEUE Canonical Terminology and Replay Lexicon v0.4.
