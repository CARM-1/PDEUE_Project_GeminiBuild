# PDEUE Interactive Learning Companion Design Specification

Version 0.2 | October 2, 2026 | Limited revision for external QB implementation-content acceptance

Prepared by ChatGPT Work as design, content, and narration agent. Codex Cloud is the future implementation agent. This package specifies a reusable learning experience that supplements the accepted Member Quickstart. It authorizes no implementation, financial action, or deployment.

## 1 Review decision and source control

The design uses a deterministic learning layer with Guided and Explore modes, three explanation depths, accessible equivalents, and optional practice. An optional AI Tutor is a separate, disabled-by-default extension. Reading, replaying, navigating, using hotspots, checking answers, and restoring learning progress require no inference.

Source baseline: PDEUE_USER_QUICKSTART_FINAL_CANDIDATE_v0.3.md and .docx, the twelve approved visual panels, PDEUE_MEMBER_DOCUMENTATION_EVIDENCE_MATRIX_v0.3.xlsx, and PDEUE_MEMBER_GRAPHIC_ASSET_REGISTER_v0.2.xlsx, retrieved from PDEUE_MEMBER_QUICKSTART_FINAL_QA_PACKAGE_v0.3.zip. The current assignment establishes acceptance of v0.3 as an eligible baseline. No promoted v1.0 artifact was verified in this work; v1.0 is not required to use accepted v0.3.

The complete retrieved R1 assignment records the controlling PDEUE-ADJUDICATION-20261001-01-FINAL rulings. The accepted evidence matrix retains historical provenance at caf1ccde52c81cd42e297b7767cb7ae7b4607c71. This revision reconciles the specified Member-risk, routing and residual changes read-only against CARM-1/PDEUE_Project_GeminiBuild, main pinned at 11069d3f66a40cc2a64a72a5e48a9df118847ca0. Subsequent main changes were not followed. Repository tests were inspected as source where relevant, not executed. See PDEUE_INTERACTIVE_SOURCE_RECONCILIATION_v0.2.md for precise locators and evidence limits.

Lexicon v0.5 is OFFICIALLY RATIFIED AND BINDING. OQ-01 is CLOSED — VERIFIED BY EXTERNAL QB. The QB independently retrieved docs/PDEUE_Canonical_Terminology_and_Replay_Lexicon_v0.5.md and found no material contradiction in the relevant design, narration, glossary and handoff definitions. This closure is recorded from the supplied QB Revision Directive v0.2, not claimed as a new independent Lexicon audit by this production agent. No unresolved source-verification question remains.

Authority order: the QB Revision Directive v0.2 controls revision scope and the specified current-main deltas; the October 1 adjudication controls resolved rules; Lexicon v0.5 controls terminology; the accepted Quickstart controls educational content; figures and the matrix establish depiction and evidence boundaries. Any genuinely new contradiction must be recorded for QB adjudication. The v0.1 design received PASS WITH LIMITED CORRECTIONS; only the identified revisions await implementation-content acceptance. Implementation remains unauthorized.

Controlling lineage: PDEUE_INTERACTIVE_LEARNING_COMPANION_DESIGN_PACKAGE_v0.1_20261002.zip is the sole v0.1 parent. This v0.2 package preserves its 36 full-course figure scripts, D1/D2/D3 model and nine-script bounded prototype media contract. PDEUE_MEMBER_LEARNING_COMPANION_QB_DESIGN_PACKAGE_v0.1.zip is SUPERSEDED / REFERENCE-ONLY DESIGN LINEAGE and is not a Codex implementation contract. Its alternative narration decomposition, media contract and test count are excluded.

The retired five-file factory spine is historical lineage, not a dependency for this assignment. This work serves the Member education and decision-packet branch across PDEUE's broader architecture, not a weather-only product. It prepares gear A through the Codex handoff, gear B through explicit source and tutor boundaries, gear C through reusable content contracts, and gear E through an optional tutor seam. Gear D receives no runner work. A single package compresses design, narration, asset provenance, and acceptance cases, removing the need for the owner to relay separate financial interpretations. Product implementation, integrations, inference calls, trading, account changes, and deployment remain blocked. The proof is the reviewed document package and its integrity report; stop after external QB handoff.

## 2 Learning experience

Entry screen offers Start Guided, Explore topics, and Resume learning when a compatible local record exists. It states: “Learning demonstration. These examples do not change an account.” No identity, account credentials, or balance connection is required. Audio starts only after Play narration or Start narrated lesson is deliberately activated.

Guided order follows the Quickstart: Welcome; SCMA isolation; Transaction Profit Waterfall; Member Wealth Desktop; Trajectory Curve; Concentric Asset Engine Rings; 87/10/3 Radar; Capital Safety Stack; Downward-Only Risk Governor; High-Watermark and IFAS; Distribution Gateway; Support and Authority; Status and Safety; First Session Checklist. The twelve figure lessons map to M-01 through M-10, with M-04a/b/c as separate panels. Welcome and the checklist use accepted Chapters 1, 11, and 12 without inventing extra figures.

Guided mode advances within a lesson after explicit Play, keeping animation synchronized to narration. At lesson end it stops and exposes Continue, Back, Replay, Practice, and Explain in more detail. It never automatically starts the next lesson's audio. Knowledge checks are optional and skippable. Switching depth or topic pauses playback and loads the selected lesson at its beginning; returning to the prior depth restores its paused position. Back and Continue preserve learning preferences, not financial simulation mutations across topics.

Explore mode shows topics grouped as Account and allocations, Desktop views, Risk and safeguards, and Flows and help. Search matches a bundled list of titles, approved terms, and friendly labels. Every result has a direct topic/depth link. There is no completion prerequisite. Hotspots select an explanation; they do not secretly start audio or invoke AI. Returning to Guided mode resumes the last Guided location, paused.

READ presents the full depth-specific text and static figure. WATCH uses the same script and visual cues with optional narration. LISTEN exposes the same narration with descriptive wording sufficient without viewing. EXPLORE exposes topic navigation and figure explanations. PRACTICE presents fixed fictional scenarios and feedback. ASK first offers bundled questions and “Explain this another way”; only an explicitly selected future AI option may call a model. These six affordances share one lesson source and never create six conflicting accounts of the rules.

Depth 1 answers “What am I looking at?” in about 30 seconds. Depth 2 answers “How does this work?” in about two minutes, including short figure-reading pauses where specified. Depth 3 supplies terminology, mechanics, constraints, examples, and authority boundaries without a fixed time limit. The narration document supplies all three depths for every figure lesson. Estimated durations are planning estimates at 125 words per minute, not measurements of audio that does not yet exist.

## 3 Layout and interaction design

Wide screen, 1024 CSS pixels and above: header with title, learning-only label, mode, and preferences; topic navigation at left; main lesson with heading and depth selector; central figure; explanation and transcript below; transport controls and Back/Continue beneath content. Optional Ask opens a side panel without covering the active figure. Reading line length is approximately 60–80 characters. Font defaults to 18 CSS pixels with scalable spacing.

Tablet, 600–1023 pixels: topic list collapses into an explicitly labeled button. The figure precedes its explanation. Ask and glossary open as inline sections. Narrow screen, 320–599 pixels: one column, text equivalent before an optional enlarged figure, transport controls wrap, and topic navigation opens in document order. No important text is shrunk to fit a desktop screenshot. Pinch zoom remains available; a separate descriptive list makes screenshot labels readable without zoom.

Tab order follows visible reading order: skip link, header controls, topic selection, depth, learning content, hotspot list, practice, transcript, transport, navigation. Focus moves to the new lesson heading only on deliberate navigation. Updating captions never steals focus. A hotspot toggles a named inline disclosure; Escape closes it and restores focus. The original screenshot remains unchanged; new highlights and explanations occupy a separate learning overlay or adjacent list.

All interactive teaching controls use “Practice” or “Learning example” labels. Chapter B uses “Apply practice reduction,” never an unqualified operational button. Reset says “Reset this learning example”; it cannot be mistaken for a Member risk-restoration permission. Financial examples are fixed fixtures, not personal calculations, predictions, or recommendations.

## 4 Deterministic architecture and component inventory

The future presentation shell may use HTML, CSS, and JavaScript, but this package contains no application implementation. SVG layers, approved screenshots, text, quiz keys, audio, caption files, and navigation records are versioned static assets. No remote fonts, media streams, analytics, account lookup, or network-dependent glossary is required for ordinary learning.

| Component | Responsibility | Boundary |
| --- | --- | --- |
| Learning shell | Modes, topic navigation, layouts, depth selection | No product account state |
| Lesson registry | Stable IDs, source locators, script revisions, dependencies | Reject unknown IDs |
| Scene presenter | Static figure and cue-selected emphasis | Never calculate official entries |
| Transport | Play, pause, resume, replay, speed, mute | User-initiated audio only |
| Transcript and captions | Exact approved spoken copy plus visual descriptions | One script revision per audio asset |
| Hotspot and glossary panel | Named keyboard-accessible explanations | Bundled text only |
| Practice presenter | Fixed scenarios and deterministic feedback | Learning state only |
| Progress store | Optional device-local learning history | No banking or Member identifiers |
| Fallback presenter | Readable static and text equivalents | Never replace missing facts with zero |
| Tutor adapter seam | Future explicit, metered contextual questions | Disabled in prototype |

Each future lesson record must supply ID, title, order/group, depth, source document and section, figure ID, evidence classification, script ID/version, cue IDs, transcript ID, caption ID, audio asset ID or unavailable status, hotspot IDs, quiz IDs, and static-equivalent text. These are data-contract field definitions, not implementation code. Invalid or mixed-version records cannot play; the source text remains available with a plain explanation.

## 5 State and timing contract

Learning state consists of content version, mode, selected topic, selected depth, per-depth playhead, transport state, selected hotspot, caption preference, transcript expansion, playback rate, mute, motion preference, quiz selection and result, viewed topics, and optional completed checklist items. Practice state is separate and reset on chapter entry. Opening practice pauses lesson media and disables narration Play until Return to lesson. Fixed scripts always narrate their canonical source examples, never a different practice fixture. Practice has its own readable explanations and explicit step navigation. No field represents actual balance, actual risk authority, trade approval, or payment status.

Transport states are ready, playing, paused, ended, loading, and unavailable. Loading is not permission to autoplay. A content change returns to ready. Audio time is the master clock while narration plays. Scene state is derived from the selected cue and absolute playhead, not a sequence of accumulated animation side effects. Seeking backward, replaying, or changing speed therefore yields the same displayed values. Each cue has start and end offsets established after approved audio production. Missing cue data disables synchronized playback and leaves readable text; Codex must not fabricate final timings.

Silent Watch uses the same cue timeline only after Play animation is activated. Listen uses the identical audio and descriptions without animation. A user selecting reduced motion receives immediate discrete scene changes with all text retained. On browser backgrounding, pause all playback; on return remain paused. Opening glossary, practice, or Ask pauses playback. Only explicit Resume restarts it.

| Event | Result | Required guard |
| --- | --- | --- |
| Play | Ready or paused to playing | Valid local media; explicit gesture |
| Pause | Playing to paused | Freeze media and cue time together |
| Replay | Playhead zero, ready | Does not reset practice; Play required |
| Seek to cue | Target cue, paused | Cue belongs to current script revision |
| Change speed | Same media position, new rate | 0.75, 1, 1.25, 1.5, or 2 times |
| Switch topic or depth | Pause old, select new | No carryover audio |
| Open hotspot | Pause and disclose text | Focus stays on initiating control |
| End narration | Ended | Continue waits for user |
| Media fails | Unavailable | Transcript and static figure remain |
| Clear progress | Empty learning record | Explicit confirmation; no account effect |

Default progress is session-only. “Remember my learning on this device” enables local persistence, without sign-in or synchronization. Save only content version, topic/depth, paused playhead, preferences, viewed/completed IDs, and quiz completion. A reload never autoplays. If storage is denied, use session state and explain that progress will not be retained. A content-version mismatch retains accessibility preferences but resets affected progress and all practice; explain why. Completion records learning participation, never qualification, permission, or a financial credential.

## 6 Financial and governance invariants

Transaction Profit Waterfall applies to a declared eligible realized and reconciled positive basis. It allocates 87% to Self-Contained Member Account (SCMA), 10% to Central Familial Common Pool (CFCP), and 3% to Founder/Chief Administrator Endowment Pool (FAEP). ADR-008 requires exact-cent conservation; canonical residuals belong to CFCP. A losing settlement has no negative 87/10/3 split; the loss stays in the executing SCMA. Principal, an arbitrary account total, pending results, and unrealized gains cannot silently become the positive allocation basis.

Chapter A offers fixed whole-dollar fixtures only and teaches the canonical CFCP residual rule in words. At the pinned revision, settlement implementation floors the SCMA 87% and FAEP 3% shares and assigns the remaining eligible cents to CFCP; the inspected settlement test source also asserts this behavior. This updates provenance without changing the educational rule or adding fixtures. A generalized amount calculator and fractional-cent worked example remain excluded from the bounded prototype.

Chapter B preserves the distinct 5.0% Tier-1 defensive per-opportunity ceiling and the Member 0.50%–2.00% downward-only operational setting. Its practice begins at 1.50%, permits reductions to 1.00% or 0.50%, and rejects restoration to a higher practice value. These three selectable values are teaching presets, not an assertion of the production slider's increment. Separate governance controls restoration; it is not automatic. Lowering a setting does not cancel filled positions or reverse settlements.

BFROZEN teaches a frozen/governance-clamped Member state displaying 0.00%, with the Member slider and Apply Reduction controls disabled. It is outside the ordinary 0.50%–2.00% operational range, is not Member-selected, grants no restoration or freeze-release authority, and proves no other safeguard passed. BCUSTODIAL teaches that a custodial SCMA cannot use ordinary Member self-service risk adjustment; current implementation requires F2-H Head of Household authorization. That authorization does not bypass any other applicable governance or immutable risk constraint. Both use deterministic text/practice states, with no fabricated screenshot or Member practice mutation.

All seven safety layers remain applicable: documented edge and qualification; Quarter-Kelly; Tier-1 ceiling; Member setting; concentration/liquidity; 40% dry powder; and governance/quarantine/halt. Their display order is pedagogical, not a claim about engine execution order. The strictest applicable limit controls and may permit zero. The dry-powder floor preserves at least 40% of applicable pre-dispatch equity as uncommitted capital after reservations and proposed commitments, with upward cent rounding. It is not principal insurance or an instruction to invest the other 60%.

Active Float is capped at $25,000 per SCMA, not total wealth. IFAS means Independent Financial Accounting and Authoritative-Record System. Scheduled, staged, sent, acknowledged, and externally settled are distinct. The Green/Yellow/Red gateway classifies positive requests: $0.01–$100.00, $100.01–$500.00, and above $500.00. Yellow adds impact awareness and F1 notice; Red adds 24-hour cooling-off and authorized F2-H co-signature plus applicable governance. No animation treats a completed timer, approval, or receipt as completed payment.

High-watermark means a defined retained-capital threshold used to govern a scheduled sweep of eligible settled balance. Under the adjudicated Member architecture, the Active Float high-watermark is $25,000 per SCMA; the cap does not limit total Member wealth. The threshold is not proof of external transfer completion.

The companion does not narrow the final PDEUE production objective: governed autonomous execution remains a separate system objective after its required gates. Learning mode supplies no execution authority and does not simulate go-live approval.

## 7 Accessibility acceptance requirements

All functions must work with keyboard alone: Tab and Shift-Tab navigation; Enter or Space activation; arrow keys for native grouped choices; Escape for dismissible panels. Provide a skip link and no keyboard trap. Focus remains visible, at least a two-pixel outline with a three-to-one contrast against adjacent surfaces, and is never hidden behind transport controls.

Use headings, landmarks, named buttons, labeled radio groups, and associated form hints. Screenshots have concise alt text and nearby long descriptions. Decorative SVG paths are excluded from the accessibility tree; equivalent ordered text and hotspot buttons expose the meaning once. Announce practice result and errors politely after submission; do not announce every animation frame. Every essential hotspot also appears in the text list; no hover-only content or color-only meaning is allowed.

Body text and small labels must meet a 4.5-to-one contrast target; large text and meaningful non-text control boundaries meet three-to-one. Use navy #0B132B on white or Slate Light #F8FAFC for sustained text. Sky Blue #0284C7 may be an accent; verify its actual contrast before using it for small text. Status labels accompany color and icons. Touch targets are at least 44 by 44 CSS pixels with separation.

Captions reproduce all spoken content, including full terms and amounts. Essential visual information is spoken or supplied in an adjacent description. Provide a complete selectable transcript at every depth. Caption display supports wrapping and user text scaling without covering amounts. Transcript links pause and seek to the corresponding cue. Speed controls preserve pitch where supported; unsupported speed is explained without removing the transcript. Mute is distinct from pause and never restarts playback.

Honor the operating-system reduced-motion preference initially and provide an explicit override. Reduced motion removes moving arrows, growth, tweening, and camera effects; use immediate emphasis and a numbered sequence. Static mode exposes every state as text, including loss, blocked increases, and halt. Neither animation nor hearing is required to answer a check.

Verify 200% text enlargement and reflow at 320 CSS pixels, including at 400% browser zoom on a suitable wide viewport. No loss of controls or mandatory two-dimensional scrolling for lesson text. A large screenshot may have its own enlargement view, but its equivalent text must reflow. Screen-reader checks cover a Windows screen reader with a supported browser and a mobile screen reader; exact tested versions belong in the future test return, not claims in this design.

## 8 Narration and media production inputs

The narration document is the spoken-copy master. Each figure has N-M-xx-D1, D2, and D3 script IDs and numbered paragraph cues. Standard lessons introduce full canonical names where needed; the glossary supplies expansions at every depth. Acronyms are spoken as letters. Read 87/10/3 as “eighty-seven, ten, three”; 0.50% as “zero point five zero percent”; 1.50% as “one point five zero percent”; 5.0% as “five percent”; $25,000 as “twenty-five thousand dollars.” IFAS is read as letters in this candidate. Do not read authoring notes aloud.

After QB approval, produce prerecorded local audio, a verbatim transcript, and WebVTT captions from the same script revision. Audio production is future work and was not performed here. Recommended delivery is one MP3 per topic/depth with an archived lossless master, no music, and consistent comfortable speech level. Verify every canonical term, number, negative clause, and authority limit by listening. Record actual durations and cue offsets; caption-to-audio alignment target is within 250 milliseconds at normal playback and scene emphasis within 300 milliseconds. At alternate rates use media time, not independent wall-clock timers.

Pauses for figure reading are explicit producer notes, not empty filler. Do not lengthen a short explanation by inventing financial details. Depth 2 aims for roughly 90–150 seconds at normal playback including planned short pauses. If the final voice duration falls outside that band, adjust pace or review the text with QB before changing meanings.

## 9 Optional AI Tutor and future voice seam

“Explain this another way” first selects a bundled alternative explanation: deeper approved text, glossary, or a prerecorded FAQ. Its label distinguishes “Recorded explanation — no AI” from “Ask AI — optional usage.” The deterministic default remains fully usable when AI is absent, disabled, offline, over budget, or declined.

Future tutor context may include content version, topic ID, depth, selected public glossary term, and user-entered question. It must exclude Member identifiers, balances, credentials, account histories, and other Members' data. An explicit send action and displayed metering notice are required. Responses are educational, source-linked, and subordinate to approved content; unsupported rules receive an uncertainty message and human support route. The tutor has no execution tools and cannot alter learning source text, financial settings, roles, quizzes, or completion authority.

Future voice separates speech recognition, model inference, and generated speech as separately visible metered capabilities. Microphone permission follows a deliberate user action, with persistent recording indication, Stop, and cancel. Present recognized text for correction before sending. Stopping voice cancels capture and future output; explain any already incurred usage. No always-listening mode. Retention, provider, budget ceiling, and service choices require a separately authorized integration assignment. None are selected or activated here.

## 10 Failures and graceful degradation

Missing audio: keep Read, transcript, static figure, Explore, and Practice; show “Narration unavailable.” Missing SVG: show approved PNG and ordered text. Missing PNG: retain the full textual equivalent, never substitute generated screenshot imagery. Unknown quiz key: disable only that question and explain unavailable feedback. Corrupt or mismatched content: stop the affected lesson's interactive playback; identify the content version to support. Local storage failure: session-only learning. AI failure: return to bundled explanations without automatic retries or paid fallback calls.

Any practice rejection leaves the last accepted practice state intact and states the reason. A successful learning interaction cannot generate a financial-looking receipt or pretend to update a Member record. Source disagreements stay in the QB review materials, not learner-facing warnings about internal engineering disputes.

## 11 Review gates and definition of done

Design-package completion means all twelve panels have purpose, source, ordered visual treatment, hotspots, three narration depths, transcript mapping, static fallback, a check, and accessibility instructions; both prototype chapters have fixed state transitions, fixtures, and expected tests; every included source asset has a measured hash; no executable application code is supplied.

Future prototype acceptance requires explicit implementation authorization first, QB acceptance of this v0.2 content, exact approved asset/script versions, functioning deterministic modes and fallbacks, all existing fixtures plus BFROZEN and BCUSTODIAL, and recorded passes for T01–T26. Lexicon source verification is closed by the external QB. Record actual browser and assistive-technology results with screenshots or recordings. No runtime, accessibility-conformance, synchronization or Windows test pass is claimed by this design-only package.

The external QB should review the limited v0.2 corrections and accept or return the implementation-content freeze candidate. Source-verification questions are NONE / CLOSED. This return stops at QB acceptance and does not initiate Codex implementation, audio generation or deployment.