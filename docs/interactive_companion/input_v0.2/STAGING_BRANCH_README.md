# PDEUE Interactive Companion Input Staging Branch

**Directive:** PDEUE-DIR-20261002-01  
**Branch:** `docs/interactive-companion-input-v0.2`  
**Base:** `main@5b2a29001a554d1fe9be661dad6c760b9311dd95`  
**Purpose:** INPUT / REFERENCE ONLY for the bounded WP-6A Codex Cloud Interactive Learning Companion prototype.

## Controlling implementation input

The sole controlling Codex contract is:

`PDEUE_CODEX_TWO_CHAPTER_PROTOTYPE_HANDOFF_v0.2.md`

Read with:

- `PDEUE_INTERACTIVE_LEARNING_COMPANION_DESIGN_SPEC_v0.2.md`
- `PDEUE_INTERACTIVE_SOURCE_RECONCILIATION_v0.2.md`
- `PDEUE_INTERACTIVE_OPEN_QUESTIONS_v0.2.md`
- `PDEUE_INTERACTIVE_DESIGN_QA_v0.2.txt`
- `PDEUE_INTERACTIVE_SUPERSESSION_NOTE_v0.2.txt`
- `reference/PDEUE_USER_QUICKSTART_FINAL_CANDIDATE_v0.3.md`

The detached SHA-256 evidence record is staged beside these files.

The accepted complete design ZIP may also be staged in this directory as:
`PDEUE_INTERACTIVE_LEARNING_COMPANION_DESIGN_PACKAGE_v0.2.zip`
Codex may unpack it locally inside its task workspace to obtain the native DOCX/XLSX/SVG/PNG assets.

## Guardrails

- Do not merge this branch to `main`.
- Do not open a PR to `main`.
- Do not modify `backend/`, `deploy/`, or CI workflow files.
- Do not treat this branch as product implementation.
- Codex implementation must occur only in the isolated task workspace and return a standalone review package.
