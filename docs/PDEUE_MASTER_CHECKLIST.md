# PDEUE Master Completion & Verification Checklist

**Authoritative Branch:** `ring1-alpha`  
**Last Updated:** 2026-11-23  
**Rule:** An item may ONLY be marked `[x]` after its **Required Verification Gate** passes in CI or an audited deployment check.

---

## Domain A — Core Trading, Quantitative Math & Gate Qualification
- [x] **A1** | Exact-cent accounting (`ADR-008`) & 87/10/3 TPW | *Pre-Pilot* | Gate: `pytest` conservation invariants (767 tests green)
- [x] **A2** | **ADR-012 High-Water Mark & Rule A14 (100% SCMA Loss Isolation)** reconciled across ledger code, UI simulators, and manuals | *Pre-Pilot* | Gate: Unit tests proving 0% CFCP/FAEP skim during drawdown recovery and 100% SCMA loss containment (`test_adr012_high_water_mark.py`, 779 backend + 16 Playwright E2E green)
- [ ] **A3** | `B4-RSK` (2-tier risk), `B4-FIN` (slippage barrier), `B7-EXE` (velocity) granular + system harness verification | *Pre-Pilot* | Gate: Isolated + end-to-end harness tests
- [x] **A4** | `OBSERVED_L2` dual-venue capture & zero-synthetic audit (Plays #11B–15B) | *Pre-Pilot* | Gate: SHA-256 manifest verification + `synthetic_fills_present: False`
- [ ] **A5** | **Gate G2 candidate schemas (Draft 2020-12), `A01–A26` adversarial rules & WP-8V charter** committed to `ring1-alpha` | *Pre-Pilot* | Gate: Committed versioned specs + independent 3rd-party Umpire audit
- [ ] **A6** | Live `fleet_engine.py` execution wiring + 12-Category 3-Tier Promotion Gateway | *Post-Pilot* | Gate: Category admission tests + concurrent mutex stress test
- [ ] **A7** | Phase 2 Multi-Asset Adapters (T-bills/money markets, equities, CME futures, crypto basis) | *Scale Phase* | Gate: Adapter contract tests + replay qualification

## Domain B — Operational Hosting, Security & Bot-Defense
- [x] **B1** | Fail-closed Docker container (`paper` mode, `read_only`, `fleet_engine.py`, persistent `soak-state` volume) | *Now (Play #17)* | Gate: `/health` 200 OK + `health_summary.json` persistence (`f4c54c6`)
- [x] **B2** | Isolated AWS Lightsail host (`pdeue-ring1-paper`) deployed in fail-closed paper/observation mode | *Now (Play #17)* | Gate: Live deployment on `pdeue-ring1-paper` (fail-closed `paper`/`observation` mode), heartbeat-based `pdeue-l2-collector` healthcheck, verified dual-venue `OBSERVED_L2` discovery & tape write (`test_b2_paper_deployment.py` + `docker compose config` green)
- [x] **B3** | Zero-CDN & zero-banking-credential hygiene gate (`Play #16B`) | *Pre-Pilot* | Gate: `backend/tests/test_play16_security_hygiene.py` green in CI
- [ ] **B4** | Dark-by-default zero-trust access (Tailscale/WireGuard or Cloudflare Access) | *Pre-Pilot* | Gate: External port scan confirms 0 open public admin ports
- [ ] **B5** | Hardware MFA (FIDO2/YubiKey), canary/honeypot endpoints, pinned dependencies | *Pre-Pilot* | Gate: Negative auth test + canary alert trigger test
- [ ] **B6** | Ephemeral `CredentialBroker` live-key wiring + Owner-Gated $100 Founder Micro-Pilot | *Owner-Gated* | Gate: Explicit Gate G1 sign-off + 20 live maker fills reconciled to the cent via IFAS
- [ ] **B7** | Production Cloud Scale (ECS Fargate, RDS Postgres Multi-AZ, S3 Object Lock WORM) | *Scale Phase* | Gate: IaC deploy + WORM immutability verification

## Domain C — Member Onboarding & Role / Authority Tier Matrix
- [x] **C1** | **5-Stage Member Onboarding Pipeline** (`[+ Onboard Member]` modal & batch ingest on `/dashboard`, 48h invite tokens, first-run Platform Orientation & Pay-It-Forward view on `/member`, `/companion` certification gate, `EXT-REF-...` funding instructions) | *Ring 1 Alpha* | Gate: Playwright E2E onboarding walk (Admin -> Member) (`test_c1_member_onboarding.py` + `tests/e2e/test_c1_onboarding_e2e.py`, 806 backend + 18 Playwright E2E green)
- [x] **C2** | **Directive R-06 Active-Hat Context Switching** & strict non-admin navigation siloing | *Ring 1 Alpha* | Gate: Playwright HTTP 403 isolation + JWT hat-switch tests (`test_c2_c5_authority_tiers.py` + `tests/e2e/test_c2_c5_role_matrix_e2e.py`, 869 backend + 24 Playwright E2E green)
- [x] **C3** | **Founder Quarantine Immunity** & **Supervisory Audit Lens** amber banner | *Ring 1 Alpha* | Gate: Unit + Playwright test (Founder root SCMA & identity immune across all subordinate tiers with HTTP 403 + audit log; `#D97706` read-only Supervisory Audit Lens banner verified)
- [x] **C4** | **Class T Sub-Tier Decomposition** (`T1` Monitor, `T2` Engineer, `T2-Household`, `T3` CTO + Directive R-12 `$****.**` masking) | *Full Prod* | Gate: Playwright DOM-strip + time-bounded audited CA Override + redaction assertions per tier (`test_c2_c5_authority_tiers.py` + `test_c2_c5_role_matrix_e2e.py` green)
- [x] **C5** | **Class F Sub-Tier Decomposition** (`F1` Mentor, `F2-H` HoH + `is_custodial` minor locks, `F2-A` Lineage Advisor, `F3` CRO dual-sign override & CA-only resumption) | *Full Prod* | Gate: Playwright role-matrix + dual-signature API tests (`test_c2_c5_authority_tiers.py` + `test_c2_c5_role_matrix_e2e.py` green)
- [x] **C6** | **Class H 12-House Lineage Schema, 3-Stage Dormant Bicameral Veto Engine & Configurable Enclave Registry** (`SCMA -> Household -> House (1..12) -> CFCP`, `/lineage/house/{id}`, `H1` R-12 masking vs `H2` sovereign desk, default `EXECUTIVE_COMMAND` fail-closed + Stage 2 advisory 9/12 + **Absolute Founder Veto** + Stage 3 binding Bicameral Veto + 1-click SHTF snap-back + configurable communal bodies & named voter seats + Immutable Core Guardrail + open-study doctrine) | *Full Prod* | Gate: Alembic 004 + relational DB hierarchy + H1/cross-house/Class-T 403 + Stage 1/2/3 & Founder/Bicameral veto + Playwright E2E (`test_c6_12_house_lineage.py` + `tests/e2e/test_c6_lineage_e2e.py`, 910 backend + 30 Playwright E2E green)

## Domain D — IFAS Banking, Distributions, Tax & FSAP / Pay-It-Forward
- [x] **D1** | ADR-011 HMAC-SHA256 Signed Outbox & `ifas_local_bridge.py` (`Play #12B`) | *Pre-Pilot* | Gate: Outbox signature, monotonicity & ACK E2E tests green
- [ ] **D2** | **Directive R-15 Three-Tier Distribution Gateway** (Green instant, Yellow Impact Card, Red 24h cooling lock + F2-H/CA co-sign) | *Ring 1 Alpha* | Gate: State-machine API tests + Playwright drawer tests
- [ ] **D3** | **Standalone IFAS Service** (`accounting.narratix.io`, isolated DB, `aud: "ifas"`, PenFed personal rail / Delaware FBO commercial custody) | *Ring 1 Alpha* | Gate: Isolated service deploy + cross-audience 403 rejection test
- [ ] **D4** | **IRS Tax Escrow (25%–30% withholding), FIFO Cost Basis & 1099/K-1 export** | *Full Prod* | Gate: Double-entry GAAP + tax-basis reconciliation tests
- [ ] **D5** | **FSAP & Pay-It-Forward** (`IF-038`–`IF-041`, variable contributor participation pool, direct-to-creditor toxic-debt payoff, 50% downstream sweep interception) | *Full Prod* | Gate: Draft-07 schema tests + downstream sweep isolation tests
- [ ] **D6** | **$25k Active Float Cap Auto-Flush** & `PlatformYieldAdapter` (idle cash / T-bill yield) | *Full Prod* | Gate: Threshold sweep trigger + exact-cent yield routing tests

## Domain E — Frontend UX, Visual Polish, Glossary/Thesaurus & System Crawl
- [x] **E1** | `DESIGN_TOKENS.md` locked in repository | *Now (Milestone 1)* | Gate: Committed to `ring1-alpha`
- [x] **E2** | **Playwright Full-System & Link Crawler** (every portal, tab, button, chart, 0 console errors, 0 dead links, 0 CDN tags) | *Now (Milestone 1)* | Gate: GitHub Actions CI + scheduled crawl green with screenshots
- [x] **E3** | **Member Desktop (`/member`) & Admin Cockpit (`/dashboard`) Polish** (real charts, Concentric Asset Rings, zero overlapping tables) | *Ring 1 Alpha* | Gate: Playwright desktop (`1440x900`) & mobile (`390x844`) zero-overflow, Concentric Asset Rings SVG & compounding chart sign-off (`test_e3_e5_ux_and_lexicon.py` + `tests/e2e/test_e3_e5_ux_e2e.py`, 924 backend + 34 Playwright E2E green)
- [x] **E4** | **Interactive Glossary/Thesaurus & Pure-CSS Hover Tooltips** (`<abbr data-tooltip>`, `ⓘ` icons, consolidated `Lexicon v0.5` in `ring1-alpha`) | *Ring 1 Alpha* | Gate: `GET /api/v1/portal/glossary` + pure-CSS `<abbr class="pdeue-term" data-tooltip>` + `ⓘ` across all 5 portals + zero-network client-side Glossary Drawer search verified in Playwright (`test_e3_e5_ux_and_lexicon.py` + `tests/e2e/test_e3_e5_ux_e2e.py` green)
- [x] **E5** | **Fail-Closed `ReadModelEnvelope[T]` UX** (`NOT AVAILABLE - QUALIFICATION PENDING`, `TRADING HALTED: DIRECTIVE R-04 ENGAGED`) | *Ring 1 Alpha* | Gate: Standardized `ReadModelEnvelope[T]` (`OK`/`QUALIFICATION_PENDING`/`TRADING_HALTED`/`DEGRADED_RETRYING`), zero native `alert()`/`confirm()`, and Playwright R-04 halt + HTTP 503 fault-injection fail-closed tests green (`test_e3_e5_ux_and_lexicon.py` + `tests/e2e/test_e3_e5_ux_e2e.py` green)

## Domain F — Multi-Tiered AI Assistants (`unilateral_execution = False`)
- [ ] **F1** | **Modular `BaseLLMClient` Adapter** (`GeminiClient`, `OpenAIClient`, `MockClient` for $0 deterministic CI) | *Full Prod* | Gate: Unit tests with `MockClient` + prompt-injection boundary test
- [ ] **F2** | **Class M — Member AI Literacy Tutor** (novice analogies, Yellow-Tier Impact Cards, `#clearTutorBtn` zero-network reset) | *Ring 1 Alpha* | Gate: Playwright live query + zero-network DOM clear/focus check
- [ ] **F3** | **Class F & T — Role-Scoped Copilot** (What-If risk modeling, NL telemetry log query, automated dual-control audit transcription) | *Full Prod* | Gate: Cross-role leak negative test + Action Card test
- [ ] **F4** | **Chief Admin — AI Chancellor Coach** (Constrained Policy Decision Matrix + `AUTH-01`–`AUTH-04` Action Cards) | *Full Prod* | Gate: Negative test proving AI cannot execute state mutations
- [ ] **F5** | **Research Studio — Live Web & "Hunch" Dossier** (3-point validation saved/editable on Tab 3 Velocity Radar) | *Full Prod* | Gate: End-to-end dossier save/edit/invalidate test

## Domain G — PDEUE University, Community Hearth & Documentation Suite
- [ ] **G1** | **PDEUE University (`/companion`)** — 3 Colleges, 6 interactive chapters, certification badges, quiz + Canon Cheat Sheet (reconciled to `ADR-012`) | *Ring 1 Alpha* | Gate: `test_interactive_companion.py` + Playwright walkthrough
- [ ] **G2** | **Pre-Rendered Voice Narration (`.mp3`) & Multi-Modal Slides/Video Slots** | *Full Prod* | Gate: Offline `<audio>` scrub sync + zero-CDN check
- [ ] **G3** | **Lineage Community Hearth (`/community`) & Sandboxed Jitsi Classroom** (Benefactor's Letter, reunions, zero trading-DB links) | *Full Prod* | Gate: Air-gap DB isolation test + iframe sandbox audit
- [ ] **G4** | **4 Illustrated Role Manuals** (`USER_QUICKSTART` v1.0 closure + `CHIEF_ADMIN`, `CLASS_T`, `CLASS_F` reconciled to `ADR-012` & `Lexicon v0.5`, DOCX/PDF + SHA-256) | *Full Prod* | Gate: Detached SHA-256 parity + Word/PDF visual sign-off
