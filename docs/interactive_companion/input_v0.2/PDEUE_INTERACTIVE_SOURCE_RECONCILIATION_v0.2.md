# PDEUE Interactive Source Reconciliation

Version 0.2 | October 2, 2026 | Read-only inspection

Repository: CARM-1/PDEUE_Project_GeminiBuild, branch main.
Reconciliation pin: 11069d3f66a40cc2a64a72a5e48a9df118847ca0. No later main revision was followed.
Historical accepted Quickstart pin: caf1ccde52c81cd42e297b7767cb7ae7b4607c71.

## Authority and closure

QB Revision Directive v0.2 is included in this package. It closes OQ-01 as CLOSED — VERIFIED BY EXTERNAL QB after direct Lexicon v0.5 review. This record attributes that verification to the external QB. No source-verification questions remain open. The approved_reference matrix and register retain their original bytes and historical statuses; this reconciliation records the specified current evidence updates without rewriting that archive.

## Pinned evidence

### backend/app/api/v1/member.html

Blob: 6068ebd80b7cbed6bfbb62274ebacb24371c3f45

loadState and showRisk: riskHalted from quarantined/is_frozen; slider and riskSubmit disabled; halted display 0.00%; ordinary range remains separate. This is source-code evidence, not a new runtime screenshot.

Source: https://github.com/CARM-1/PDEUE_Project_GeminiBuild/blob/11069d3f66a40cc2a64a72a5e48a9df118847ca0/backend/app/api/v1/member.html

### backend/app/api/v1/portal_router.py

Blob: 36e6dfa77fc8bf86c2a2a942b393f91b0822c50d

get_member_state around lines 548–567 clamps returned risk_dial_pct to 0.0 when frozen, including parent-house quarantine. update_current_member_risk_dial around lines 635–664 rejects custodial adjustment with F2-H Head of Household authorization required. Existing alternate legacy paths are not teaching authority for expanding the approved Member lesson.

Source: https://github.com/CARM-1/PDEUE_Project_GeminiBuild/blob/11069d3f66a40cc2a64a72a5e48a9df118847ca0/backend/app/api/v1/portal_router.py

### backend/app/api/v1/dashboard.html

Blob: b5ccbdfde488da33a3330cd5709bc2850facec25

Line 574 Member link uses /member?scma_id=... . Routing seam closed for the inspected Chief Administrator link; no added lesson.

Source: https://github.com/CARM-1/PDEUE_Project_GeminiBuild/blob/11069d3f66a40cc2a64a72a5e48a9df118847ca0/backend/app/api/v1/dashboard.html

### backend/app/domain/settlement_engine.py

Blob: 68f5f74c009b65fa3557563a42d454c25c6a92b7

calculate_waterfall_split, lines 17–40: floors positive SCMA 87% and FAEP 3%, adds all indivisible residual cents to CFCP, conserves total; nonpositive result stays SCMA with zero shared allocations. Canonical CFCP residual now has implementation support as well as governance support. Legacy noncanonical names in implementation comments do not override the ratified Lexicon.

Source: https://github.com/CARM-1/PDEUE_Project_GeminiBuild/blob/11069d3f66a40cc2a64a72a5e48a9df118847ca0/backend/app/domain/settlement_engine.py

### backend/tests/test_phase4_settlement_waterfall.py

Blob: 89da923f306bc47378c1858cfcab4859ae4cf925

Source assertions specify SCMA 334014, CFCP 38394 and FAEP 11517 cents for 383925 eligible cents; also assert loss containment. This test source was read, not run. No test-execution pass is claimed.

Source: https://github.com/CARM-1/PDEUE_Project_GeminiBuild/blob/11069d3f66a40cc2a64a72a5e48a9df118847ca0/backend/tests/test_phase4_settlement_waterfall.py

## Bounded result

No educational waterfall rule change; all five Chapter A fixtures retained unchanged. All seven prior Chapter B fixtures remain, with BFROZEN and BCUSTODIAL added. No engine-conformance, venue-adapter, qualification, credential or operational-control content was added. No product endpoint, daemon, test suite or financial operation was executed. Repository retrieval was read-only; source files were never imported or run.

## Narration preservation

36 figure scripts and 72 paragraph cues retained. Exactly four figure scripts changed through five cue paragraphs: N-M-06-D1-C01, N-M-06-D2-C03, N-M-06-D2-C04, N-M-06-D3-C01 and N-M-10-D2-C03. The other 32 figure scripts and opening/closing spoken copy are byte-for-byte identical as paragraph text. Updated planning durations are estimates, not produced audio. The prototype remains nine scripts; practice states add no audio contract.