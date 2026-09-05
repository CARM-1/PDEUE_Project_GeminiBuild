# PDEUE Canonical Terminology and Replay Lexicon v0.4

**Project:** PDEUE - Public Data Event Underwriting Engine
**Project relationship:** Project FUTURE common Financial Generation System role/governance terminology
**Purpose:** Eliminate ambiguity in architecture, member account governance, execution velocity, replay evidence, financial-generation-system roles, software authority, accounting-system separation, and sprint decisions.
**Status:** BINDING CANONICAL BASELINE; officially ratified September 4, 2026 (supersedes v0.3).

## 0. Change-control note
This version preserves all v0.3 economic percentages and execution terms. It corrects the informal waterfall aliases to the canonical names Central Familial Common Pool (CFCP) and Founder/Chief Administrator Endowment Pool (FAEP), while formally installing the role taxonomy, Active Hat, Split-Hat, and accounting-system separation models.

## 1. Binding language rule
The bare word **market** is overloaded and MUST NOT be used when scope depends on what is meant. Prefer: **market archetype**, **market family**, **market category/domain**, **venue**, **venue-listed contract**, **instrument**, **candidate universe**, **historical case**, **historical anchor trade/fill**, **replay decision**, or **replay trade**.

Likewise, the bare word **trade** must be qualified: **historical venue trade/fill**, **historical anchor trade/fill**, **replay trade**, **live trade**, or **paper trade**.

The bare word **administrator** MUST be qualified: **Chief Administrator**, **System Administrator Tier 1 (T1)**, **System Administrator Tier 2 (T2)**, or **System Administrator Tier 3 (T3)**.

The bare word **advisor** MUST be qualified: **Financial Advisor Tier 1 (F1)**, **Financial Advisor Tier 2 (F2)**, or **Financial Advisor Tier 3 (F3)**.

## 2. Core product and multigenerational engine terms

### PDEUE
**Public Data Event Underwriting Engine.** A governed system that converts lawful public information and market state into structured evidence, probabilities/uncertainty, opportunity selection, risk-adjusted portfolio decisions, decision packets, replay evidence, and phase-gated execution.

### Financial Generation System (FGS)
The common governed software environment and control architecture under which one or more Financial Generation Engines operate using shared identity, role, authorization, audit, policy, and controlled financial-record interfaces.

### Financial Generation Engine (FGE)
A software-based revenue-generation or capital-generation engine governed by the FGS. PDEUE is one FGE.

### Multigenerational Legacy Financial Generation Engine
The overarching purpose of PDEUE: an automated, continuous capital preservation and compounding engine operated across multiple lineal generations of a single extended family over decade horizons.

### Self-Contained Member Account (SCMA)
An isolated, tenant-partitioned ledger account belonging to an authenticated family member. Each SCMA maintains its own discrete seed principal, integer-cent cash balance, open inventory, and individual risk allocation profile. No member account can cross-collateralize or impair another member account.

### Central Familial Common Pool (CFCP)
A non-trading treasury sub-ledger that receives an automated 10% allocation from realized net trading profits across all member accounts upon winning contract resolution.

### Founder/Chief Administrator Endowment Pool (FAEP)
A dedicated administrative treasury sub-ledger owned by the PDEUE founder and Chief Administrator, receiving an automated 3% allocation from realized net trading profits across all member accounts upon winning contract resolution.

### Transaction Profit Waterfall (TPW)
The automated post-resolution accounting rule applied to gross profit (Payout - Cost Basis) on winning contracts: 87% reinvested into the executing SCMA, 10% routed to the CFCP, and 3% routed to the FAEP. Truncation remainders auto-credit the CFCP. Adverse trade losses remain 100% contained within the executing member account.

## 3. Selection, risk envelope, and execution terms

### Two-Tier Risk Envelope (B4-RSK)
A dual-layer capital protection architecture: Tier 1 enforces immutable engine safety ceilings (maximum 5% stake per trade, Quarter-Kelly sizing at 0.25 scale, and 10% correlated factor cap); Tier 2 provides an asymmetric member dial allowing risk to be configured downward (e.g., to 1% or 2%) while strictly barring upward overrides beyond system limits.

### Real-World Microstructure & Slippage Barrier (B4-FIN)
Dynamic pre-trade execution protections that evaluate resting order book depth (VWAP). If liquidity sweeps result in execution slippage exceeding 1.5% of entry price, or if spread/fees eliminate the modeled net edge, the engine trips an immediate fail-closed halt.

### Hybrid Velocity Engine (B7-EXE)
A capital recycling architecture prioritizing rapid compounding on small bankrolls. Incorporates an Expiry Horizon Filter (max_expiry_hours) and velocity-adjusted Sharpe ranking. Positions hold to maturity ($1.00/$0.00) by default to incur zero exit friction, while allowing early harvest only if resting bids capture >= 80% of maximum profit net of exit spread and exchange fees.

## 4. Wallet, accounting, and counting rules

### Exact-Cent Conservation (ADR-008)
All financial accounting across master ledgers, member sub-accounts, and waterfall pools operates on 64-bit integer cents. Floating-point currency calculations are barred from financial state transitions.

## 5. Identity, role, authority, and permission terms

### Chief Administrator
The highest human administrative and governance role within the FGS. The final human approval authority for privileged appointments and material production policy, bounded by immutable risk ceilings, SCMA isolation, and Exact-Cent Conservation.

### System Administrators (T1, T2, T3)
Technical administration hierarchy. T1 handles low-risk diagnostics; T2 manages operational services; T3 administers production infrastructure, secrets, and releases. T3 changes affecting financial logic mandate Dual Control with F3 and the Chief Administrator.

### Financial Advisors (F1, F2, F3)
Financial advisory hierarchy. F1 provides member-scoped advice; F2 manages household-level advisory bounds; F3 oversees global risk policy, strategy promotion, and financial emergency halts.

### Member User
An authenticated family member operating strictly within their own SCMA. May adjust their individual risk dial downward only; cannot access or cross-collateralize other member accounts.

### Active Hat & Split-Hat Enforcement
Explicit selection of current operating context. Multi-role individuals cannot combine technical, financial, and member privileges within a single action.

### Dual Control
A mandatory rule requiring two or more independently authenticated, qualified approvals before consequential technical, financial, or deployment actions execute.

## 6. Financial-generation/accounting separation terms

### Independent Financial Accounting & Authoritative-Record System
A physically and logically separate application that independently records and reconciles financial generation events, waterfall allocations, and external banking records. PDEUE does not store raw external bank credentials.

### Financial Generation / Accounting Boundary
A narrow, signed, one-way event interface transmitting versioned execution and settlement records to the accounting system while receiving cryptographic reconciliation acknowledgements.

## 7. Adoption rule
This v0.4 Lexicon is binding across all PDEUE development tracks, pull requests, test fixtures, and documentation. Supersedes v0.3.
