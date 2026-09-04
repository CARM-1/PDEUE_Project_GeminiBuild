# PDEUE Canonical Terminology and Replay Lexicon v0.3

**Project:** PDEUE - Public Data Event Underwriting Engine  
**Purpose:** Eliminate ambiguity in architecture, member account governance, execution velocity, replay evidence, and sprint decisions.  
**Status:** BINDING CANONICAL BASELINE for Wave 001 and Production Operations; supersedes v0.2.  
**Date:** 2026-09-04

## 1. Binding language rule

The bare word **market** is overloaded and MUST NOT be used when scope depends on what is meant. Prefer: **market archetype**, **market family**, **market category/domain**, **venue**, **venue-listed contract**, **instrument**, **candidate universe**, **historical case**, **historical anchor trade/fill**, **replay decision**, or **replay trade**.

Likewise, the bare word **trade** must be qualified when ambiguity matters: **historical venue trade/fill**, **historical anchor trade/fill**, **replay trade**, **live trade**, or **paper trade**.

If any participant or interface uses broad terminology, the Chief AI Coordinator must map it to these canonical terms before any scope-changing decision.

## 2. Core product and multigenerational engine terms

### PDEUE
**Public Data Event Underwriting Engine.** A governed system that converts lawful public information and market state into structured evidence, probabilities/uncertainty, opportunity selection, risk-adjusted portfolio decisions, decision packets, replay evidence, and phase-gated execution.

### Multigenerational Legacy Financial Generation Engine
The overarching purpose of PDEUE: an automated, continuous capital preservation and compounding engine operated across multiple lineal generations of a single extended family (originating from a common maternal and paternal pair) over decade horizons.

### Self-Contained Member Account (SCMA)
An isolated, tenant-partitioned ledger account belonging to an authenticated family member. Each SCMA maintains its own discrete seed principal, integer-cent cash balance, open inventory, and individual risk allocation profile. No member account can cross-collateralize or impair another member account.

### Central Familial Common Pool (CFCP)
A non-trading treasury sub-ledger that receives an automated 10% allocation from realized net trading profits across all member accounts upon winning contract resolution.

### Founder/Chief Administrator Endowment Pool (FAEP)
A dedicated administrative treasury sub-ledger owned by the PDEUE founder and Chief Administrator, receiving an automated 3% allocation from realized net trading profits across all member accounts upon winning contract resolution.

### Transaction Profit Waterfall (TPW)
The automated post-resolution accounting rule applied to gross profit (Payout - Cost Basis) on winning contracts: 87% reinvested into the executing Self-Contained Member Account, 10% routed to the Central Familial Common Pool, and 3% routed to the Founder Pool. Truncation remainders auto-credit the Family Pool. Adverse trade losses remain 100% contained within the executing member account.

### Public event
A real-world occurrence, release, condition, or resolution that can affect one or more tradable instruments or event contracts.

### Market archetype
A reusable class of trading mechanics (e.g., binary event/resolution contracts, continuous spot, expiring leveraged contracts, nonlinear contingent claims).

### Venue / platform
The exchange, prediction-market platform, broker venue, or lawful execution facility where contracts are listed (e.g., Kalshi, Polymarket).

## 3. Selection, risk envelope, and execution terms

### Two-Tier Risk Envelope (B4-RSK)
A dual-layer capital protection architecture: Tier 1 enforces immutable engine safety ceilings (maximum 5% stake per trade, Quarter-Kelly sizing at 0.25 scale, and 10% correlated factor cap); Tier 2 provides an asymmetric member dial allowing risk to be configured downward (e.g., to 1% or 2%) while strictly barring upward overrides beyond system limits.

### Real-World Microstructure & Slippage Barrier (B4-FIN)
Dynamic pre-trade execution protections that evaluate resting order book depth (VWAP). If liquidity sweeps result in execution slippage exceeding 1.5% of entry price, or if spread/fees eliminate the modeled net edge, the engine trips an immediate fail-closed halt.

### Hybrid Velocity Engine (B7-EXE)
A capital recycling architecture prioritizing rapid compounding on small bankrolls. Incorporates an Expiry Horizon Filter (max_expiry_hours) and velocity-adjusted Sharpe ranking. Positions hold to maturity ($1.00/$0.00) by default to incur zero exit friction, while allowing early harvest only if resting bids capture >= 80% of maximum profit net of exit spread and exchange fees.

### Platform scan / discovery scan
The low-cost step enumerating the eligible candidate universe and collecting lightweight state for first-pass filtering.

### Selector decision
A PDEUE output before deep underwriting: ENGAGE, INVESTIGATE, REJECT, or ABSTAIN.

### Selection Alpha
Economic value attributable to choosing which opportunities to pursue or reject before measuring forecast, entry, or position-management skill.

## 4. Historical replay and evidence lineage terms

### Historical case
One real settled/resolved historical contract/instrument plus the bounded market/evidence history required for replay.

### Historical anchor trade/fill
A historical venue trade/fill selected to define a replay decision timestamp without revealing subsequent price trajectory or ultimate resolution.

### Replay decision
One PDEUE decision at one historical decision point using only evidence eligible at that instant.

### Continuous wallet replay
Replay mode where PDEUE advances through a historical period with a persistent wallet and open-position state, accumulating all gains, losses, and capital constraints.

### Point-in-time evidence
Evidence tagged with provenance showing event time, publication/release time, revision time, and retrieval time. Models and screeners must not observe data before its recorded availability.

## 5. Wallet, accounting, and counting rules

### Exact-Cent Conservation (ADR-008)
All financial accounting across master ledgers, member sub-accounts, and waterfall pools operates on 64-bit integer cents. Floating-point currency calculations are barred from financial state transitions.

### Counting rules
Every report must name quantities precisely: venues, categories/domains, settled historical contracts, anchor trades, candidate snapshots, selector decisions, replay trades, open positions, and abstentions. Never use "markets" or "trades" ambiguously.

## 6. Adoption and governance rule

This v0.3 Lexicon is binding across all PDEUE development tracks, pull requests, test fixtures, and documentation. Any ambiguous usage of "market", "trade", "pool", "waterfall", or "risk" must map strictly to these canonical definitions.
