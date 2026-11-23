# PDEUE Institutional Design Tokens & UI Standards (`DESIGN_TOKENS.md`)

All PDEUE web portals (`/dashboard`, `/member`, `/advisor`, `/admin/tech`, `/lineage/house/{id}`, `/companion`, `/community`) MUST conform to these tokens. Zero external CDN stylesheets or scripts are permitted.

## 1. Color Palette (PDEUE Dark Institutional Theme)

| Token | Hex | Usage |
| :--- | :--- | :--- |
| `--bg-canvas` | `#0B132B` | Primary page canvas (Deep Navy) |
| `--bg-card` | `#1C2541` | Elevated cards, drawers, modals (Steel Navy) |
| `--bg-surface` | `#1E293B` | Table headers, tooltips, secondary panels |
| `--border-subtle` | `#334155` | Card borders, dividers, input outlines |
| `--text-primary` | `#F8FAFC` | Primary headings and values (WCAG AA >= 4.5:1) |
| `--text-secondary` | `#CBD5E1` | Body prose and table cells |
| `--text-muted` | `#94A3B8` | Labels, timestamps, metadata |
| `--accent-sky` | `#38BDF8` | Interactive highlights, links, tooltip underlines |
| `--accent-sky-deep` | `#0284C7` | Primary action buttons |
| `--status-green` | `#059669` | Healthy state, Green-Tier autonomous draw, verified badges |
| `--status-amber` | `#D97706` | Yellow-Tier educational friction, Supervisory Audit Lens banner |
| `--status-red` | `#DC2626` | Red-Tier principal lock, Directive R-04 Halt, Quarantine |

*Note on IFAS Separation:* The standalone Independent Financial Accounting System (`accounting.narratix.io`) shares the typography family below but uses a light institutional fiduciary surface (`#F8FAFC` canvas, `#0B132B` headers) so operators never visually confuse trading telemetry with bank custody.

## 2. Typography & Numeric Formatting
- **Font Stack:** `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif`
- **Monospace (IDs, Hashes, Tokens):** `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace`
- **Scale:** Page H1 `1.5rem–1.75rem` (700); Section H2 `1.1rem–1.25rem` (700); Card Labels `0.85rem–0.95rem` (600, high contrast — never faint); Body `0.95rem–1.0rem` (`line-height: 1.5`).
- **Financial Figures:** Always apply `font-variant-numeric: tabular-nums;` and format integer cents strictly at the UI presentation boundary (`$X,XXX.XX`).

## 3. Role Badges, Layout & Accessibility Invariants
- **Active-Hat Pill Badges:** Every workspace header displays an unmistakable Active-Hat badge (`CHIEF_ADMIN`, `CLASS T: T1/T2/T3`, `CLASS F: F1/F2-H/F2-A/F3`, `CLASS H: H1/H2`, `CLASS M: MEMBER_USER`). Never conflate Class F2-H (Head of Household) with Class H2 (House Leader).
- **Supervisory Audit Lens:** When Chief Admin inspects a subordinate view, render a full-width `#D97706` amber banner (`SUPERVISORY AUDIT LENS — READ-ONLY INSPECTION`).
- **Table Isolation:** Wrap stacked tables in `.table-card { margin-bottom: 32px; clear: both; overflow-x: auto; }` to prevent layout collision.
- **Fail-Closed `ReadModelEnvelope[T]` States:** Never display stale cached numbers or fabricated placeholders when an endpoint is degraded or unseeded. Explicitly render:
  - `UNAVAILABLE - ENGINE UNREACHABLE`
  - `NOT AVAILABLE - QUALIFICATION PENDING`
  - `TRADING HALTED: DIRECTIVE R-04 ENGAGED`
  - `SESSION ACCESS DENIED (HTTP 403)`
- **Hover Tooltips & Glossary:** Use pure CSS `<abbr data-tooltip="...">` (dotted `#38BDF8` underline, `#1E293B` popup) and accessible `ⓘ` icons for all PDEUE acronyms and risk controls.
- **Accessible Clear Controls:** `#clearTutorBtn` and `#clearCopilotBtn` execute pure client-side DOM resets (zero `fetch`/`XHR` requests) and restore keyboard focus to the query input.
