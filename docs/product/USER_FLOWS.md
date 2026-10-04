# User flows
Only flows with branching or state. Status in trace.yaml.

### FLOW-001 First run to ready
UCs: UC-001, UC-002, UC-003, UC-005, UC-006
```mermaid
flowchart TD
  A[Open app] --> B{Readiness all must-haves?}
  B -- no --> C[Checklist: next open item + link]
  C --> D[Profile › Résumés: upload]
  D --> E[Review progress] --> F[Feedback: apply / comment / edit]
  F --> G[Make master → approve master.yaml diff]
  G --> H[Saved answers: work auth, salary]
  H --> I[Optional: writing samples]
  I --> B
  B -- yes --> J[Ready to apply → Jobs list]
```
What to notice: the checklist is the hub; every step returns to it, so a user who leaves mid-way resumes at the next open item.

### FLOW-002 Feedback item lifecycle
UCs: UC-002
```mermaid
stateDiagram-v2
  [*] --> open
  open --> applied: Apply (guard ok)
  open --> open: Apply (guard fails, reason shown)
  open --> redrafting: Comment
  redrafting --> open: new suggestion
  open --> dismissed: Dismiss
  applied --> [*]
  dismissed --> [*]
```
What to notice: nothing reaches the résumé except via `applied`, and only after the zero-fabrication guard.

### FLOW-003 Check a job
UCs: UC-010
```mermaid
flowchart TD
  A[Jobs › Check a job] --> B{paste or file ok?}
  B -- no --> B1[inline error: type / size / no text]
  B -- yes --> C[stored + scanned] --> D{flagged?}
  D -- yes --> D1[badge + Action Item; scoring continues]
  D -- no --> E
  D1 --> E[fit score + résumé match table]
  E --> F{best ≥ threshold?}
  F -- yes --> G[Use this résumé → job ready to tick]
  F -- no --> H[Tailor from master? one run]
  H -- no --> Z[keep job, no résumé chosen]
  H -- yes --> I{attempt ≥ threshold?}
  I -- yes --> G
  I -- no --> J[notice best X / needed Y + missing] --> K{Create closest anyway?}
  K -- yes --> L[keep attempt, below_threshold]
  K -- no --> M[discard attempt]
```
What to notice: max one tailor run per check; a flagged posting is still scored but can't be prepared until cleared.

### FLOW-004 Select jobs → start pipeline
UCs: UC-007 (+ USR-034; REQs to derive)
```mermaid
flowchart TD
  A[Jobs list] --> B[filter / sort optional]
  B --> C[tick jobs: row, select visible, bulk]
  C --> D[Start pipeline]
  D --> E[Review sheet: one 'Go as far as' for all (default Fill, I submit), override per row: Prepare / Fill / Submit]
  E --> F{readiness ok for fill/submit?}
  F -- no --> F1[those rows capped at Prepare, reason + link to Profile]
  F -- yes --> G
  F1 --> G[Start] --> H[Progress: per-job stage, Pause / Cancel / Retry]
  H --> I[done: Prepared / Filled (open tab) / Submitted / Needs you]
```
What to notice: one entry point (Start pipeline on the Jobs list); stop stage chosen per job; Tier A + LinkedIn never offered Submit.
