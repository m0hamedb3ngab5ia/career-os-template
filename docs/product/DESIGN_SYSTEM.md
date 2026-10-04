# Design system
TOC: Rule · Tokens · Components · Patterns · A11y · Responsive · Delta 2026-10-04 · Mockups
Source: `ui/src/styles/tokens.css`, `global.css`, `ui/src/kit` (CSS modules + CSS vars, no Tailwind).

## Rule (DEC-009)
Reuse kit components; no new component unless a delta screen can't be built from existing ones. Every frontend PR: `web-design-guidelines` (Vercel) audit + `vitest-axe`. Unused tokens/components → IA.md Trim list.


## Tokens

### Type (font: `-apple-system, SF Pro Text, system-ui`; mono `ui-monospace, SF Mono`)
| Token | px | Use |
|---|---|---|
| --fs-large-title | 34 | phone title |
| --fs-title | 26 | desktop h1 |
| --fs-stat | 28 | stat numbers |
| --fs-h2 | 15 | section h2 |
| --fs-body | 13 | default (line-height 1.45) |
| --fs-caption | 12 | secondary |
| --fs-group | 11 | group labels |
| --fs-tab | 10 | tab bar |
Some CSS modules hardcode 15/16/17px (not tokenised).

### Spacing / sizes
| Token | Value |
|---|---|
| --space-1..6 | 4, 8, 12, 16, 24, 32 |
| --sidebar-w | 232 |
| --control-h | 32 |
| --nav-h | 30 |
| --row-h | 44 |
| --touch | 44 (coarse pointer) |
Page header pad 28/32/18; body pad 0/32/32 (hardcoded).

### Radius
| Token | px |
|---|---|
| --r-chip | 999 |
| --r-card | 12 |
| --r-control | 8 |
| --r-nav | 7 |
| --r-segment | 6 |
| --r-tier | 5 |
| --r-pill | 13 |

### Color (light / dark)
| Token | Light | Dark |
|---|---|---|
| --bg | #fff | #1c1c1e |
| --group (page) | #faf9f5 | #161618 |
| --card | #fff | #2c2c2e |
| --sidebar | #f4f2ec | #232326 |
| --fill | #eeebe3 | #3a3a3c |
| --sep | #e5e1d8 | #3a3a3c |
| --label | #1d1d1f | #f5f5f7 |
| --sec | #5e5e63 | #aeaeb2 |
| --ter | #666469 | #98989d |
| --accent | #0066cc | #0064d1 |
| --link / --focus | #0066cc | #4da3ff |
| --selected | #dce7f5 | #1e3a5f |
| --hover | #f2f7fd | #34343a |
| --destructive | #c4001a | #ff6b61 |
| --toast-bg / fg | #1d1d1f / #fff | #3a3a3c / #f5f5f7 |
| --switch-on | #1e7b34 | #30a14e |

Status pairs (text / bg), chips always carry label:
| Hue | Light | Dark |
|---|---|---|
| green | #1e7b34 / #e3f4e7 | #4ade80 / #16301f |
| orange | #a34700 / #fdeedc | #ffb340 / #3a2a12 |
| red | #c4001a / #fce4e6 | #ff6b61 / #3d1a1a |
| purple | #7a3ba0 / #f1e6f7 | #d4a5f5 / #33223f |
| blue | #0058b0 / #e1ecf9 | #7cb8ff / #18304d |
| teal | #00677f / #ddf1f5 | #6ad4ea / #12343b |
| gray | #55555a / #eeebe3 | #c7c7cc / #3a3a3c |

Chart: --cat-1..4 (#2b6cb0, #c2610c, #7a3ba0, #00907f), --cat-other #8e8e93 (same both themes).
Elevation: --shadow-card/popover/tooltip/knob; dark card = 1px white 4% ring. --hover-filter/--active-filter brightness 0.96/0.9 light, 1.15/1.3 dark.

## Components (`ui/src/kit`)
Legend: D default, H hover, F focus, X disabled, L loading, E error, M empty. "?" = not verified in source.

| Component | Purpose | Variants | States |
|---|---|---|---|
| Button | action | primary, secondary, destructive, destructive-filled; regular/small; `pending`+`pendingLabel` | D H F X L |
| UnavailableButton | disabled button w/ reason | same variants/sizes | X (reason) |
| ExternalLink | safe new-tab link | - | D H F |
| chips: Chip, StatusChip, SafetyChip, PriorityChip, StopReasonChip, TierBadge, NeedsLabel, ActionTypeLabel | status labels (tone + glyph/label) | tone: 7 hues | D |
| TextInput, NumberInput, SelectInput, TimeInput, RangeInput, WithUnit, TagEditor | form inputs | integer/min/max, unit | D F X E? |
| FormField (TextField, SelectField) | label + hint wrapper | - | D F X E? |
| Switch | boolean | labelHidden | D F X |
| SegmentedControl | 2-4 exclusive options | .Option; roving tabindex | D H F X |
| PillGroup | filter pills | .Pill; roving tabindex | D H F |
| Tabs | page tabs w/ counts | .Tab, `controls` panel id; roving | D H F |
| Menu | dropdown | Trigger/Content/Item/RadioItem/CheckboxItem; regular/small | D H F X |
| Popover | anchored panel | label, anchorRef | D F (Esc) |
| Listbox | custom select | label inside/outside | D H F |
| Sheet | side/bottom edit panel | title, trailing, footer, SheetBarButton | D F (focus trap) |
| Dialog | modal | role=dialog aria-modal | D F (focus trap) |
| ConfirmPanel | inline confirm | confirmVariant, pending | D L |
| Toast / useToast | polite live toast w/ Undo | message, onUndo, seconds (default 8) | D (pause on hover/focus) |
| EmptyState | empty/error block | headingLevel, action | M E |
| Meter | labelled progress | value/max/note | D |
| Pager + usePaged | pagination | sizes 10/25/50/100 | D X |
| Details | disclosure | defaultOpen | D F |
| MarkDoneCircle | done toggle | done/undone | D H F |

Count: 22 rows listing 31 exports (chips x8 collapsed).

## Patterns
- Undo toast: reversible actions act now, toast shows Undo ~8s; one at a time; region always mounted (`role=status aria-live=polite`); timer pauses on hover/focus; focus returns on close.
- Confirm: destructive/irreversible via ConfirmPanel (inline) or Dialog; button shows `Verb...` while pending; red for destructive.
- Sheets: edits (AddItem, Due, StatusChooser, MarkConnection, Safety, SaveBar, DraftSheet); trap focus, Esc closes, focus returns to opener.
- DraftSheet: cover letter / outreach draft view with Approve/Edit/Reject; shared by Job detail, Contacts, Inbox.
- LogPane: live tail of run log in Runs/RunDetail; scrollable region.
- Empty/loading/error: `EmptyState` with title + explanation + retry/back action; pages show placeholder title with `aria-busy`, real title announced after load.
- Live updates: connection dot in sidebar (`aria-live=polite`).
- URL state: tabs, sort, filters (`f.<field>`), selected thread, settings section in query/path.
- Unsaved Settings: guarded (beforeunload + router guard); SaveBar.

## A11y
- Skip link first in shell; focus moved to h1 on route change (AppShell).
- `:focus-visible` global; accent `--focus`.
- Roving tabindex + arrows: Tabs, PillGroup, SegmentedControl; Esc closes Menu/Popover/Sheet/Dialog.
- Cmd/Ctrl+K focuses search (`aria-keyshortcuts`); skipped if modal open.
- Status never by colour alone (label/glyph); `vitest-axe` on every page test.
- `prefers-reduced-motion` honoured (global.css).

## Responsive
- No shared breakpoint token; each module sets its own.
- Breakpoints seen: 1100 (Settings, Storage, Today, JobDetail, Runs), 900 (Settings, Inbox), 640 (ActionItems), 600 (Settings, Storage, DraftSheet, Contacts).
- `@media (pointer: coarse)`: 44px targets in Today, Pipeline, Inbox, JobDetail, Contacts, ActionItems, Settings.
- AppShell: no media query -> no mobile nav (fixed 232px sidebar). Jobs table + Kanban scroll horizontally on phone.

## Delta 2026-10-04
Built from existing kit only. New = composition, not new primitives.

| need (screen) | build from | REQ |
|---|---|---|
| Readiness card (Today, Profile) | card + Meter + checklist rows w/ link; "Ready to apply" StatusChip green | REQ-102 |
| Apply disabled w/ reason | UnavailableButton (reason links to Profile item) | REQ-103 |
| Job row select + bulk bar | native checkbox in table + sticky bar w/ Button (Select / Unselect) | REQ-104 |
| Injection badge | SafetyChip tone red "Flagged"; Job detail banner + Button "I checked it" | REQ-109 |
| Check a job | Dialog + TextInput (textarea) / native file input + Meter + table | REQ-114..116 |
| Résumé match table | plain table: résumé, score, best StatusChip, reason | REQ-115 |
| Below-threshold notice | inline EmptyState-style block "best X / needed Y" + missing list + ConfirmPanel (Keep closest / Discard) | REQ-116 |
| Profile tabs | Tabs (URL state) | REQ-107 |
| Résumé upload | native `<input type=file>` + drop zone (label wraps input); inline error | REQ-093 |
| Feedback items | rows w/ Button Apply / Comment (Sheet) / Dismiss; guard reason inline | REQ-095..097 |
| master.yaml diff approve | Sheet w/ pre diff + Approve / Reject | REQ-099 |
| Fill preview | Sheet: table field/value/source, TextInput inline, Switch "save to profile", Button Fill (UnavailableButton while blocked) | REQ-105 REQ-106 |
| Deletes (version, answer, sample) | ConfirmPanel destructive | REQ-100 REQ-107 |

States per delta screen: empty (first run), loading (`aria-busy`, Meter), error (inline + Retry), success (toast).

Gaps (non-blocking, decide in TASK-013): shared breakpoint token (now 600/640/900/1100 ad hoc); no mobile nav (sidebar fixed 232px); input error prop unverified; hardcoded 15/16/17px sizes.

Table (USR-036): keep current Jobs table as-is (Excel-like: header sort + filter menus, filter chips, Pager rows 10/25/50/100). Every list of jobs reuses it.
Page header (USR-035): h1 + one-line `--sec` guidance + primary action, every screen.

## Mockups
Wireframes, minimal, existing tokens: https://claude.ai/artifact/LiWEdd7CnMgFChRLo4hCMt
| artboard | FLOW / UC |
|---|---|
| Main.dc.html (Profile) | FLOW-001 UC-001..006 UC-009 |
| CheckJob.dc.html | FLOW-003 UC-010 |
| JobsSelect.dc.html | UC-007 UC-012 |
| FillPreview.dc.html | UC-008 |
