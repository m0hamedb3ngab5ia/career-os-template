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
