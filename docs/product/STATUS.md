# Status

## Now
- Lane: Feature — onboarding + profile (USR-002..004, 022..027) + injection guard, résumé reuse, check a job (USR-033, 031, 028)
- Stage: Architecture delta (next), then Tasks → Build
- Done: REQ-093..116, UC-001..012, FLOW-001/002 approved (gates 2026-10-04)
- Next: ARCHITECTURE delta (profile store layout, résumé text extraction lib, review run, readiness API, `selected` field, untrusted wrapping + injection scan, match score + résumé reuse) + DECISIONS. Build USR-033 first
- Waiting on user: other USR triage. All Q answered 2026-10-04.
- Approved 2026-10-04: REQ-108..110 (USR-033), REQ-111..113 (USR-031), REQ-114..116 (USR-028), UC-010..012. Later: Q-008 json, USR-029/030/032

## Gates
| gate | status | date |
|---|---|---|
| Audit triage | pending | |
| Onboarding+profile spec (Feature) | approved | 2026-10-04 |
| Injection guard + résumé reuse + check-a-job spec (Feature) | approved | 2026-10-04 |

## Deletion candidates
<!-- rejected REQs whose code still exists -->
- REQ-062 Gmail auto-send: check any send path in inbox/outreach code; `qa_ext` `email_autosend_verified` stays as guard

## Trace
<!-- trace:status -->
| REQ status | n |
|---|---|
| approved | 24 |
| proposed | 61 |
| rejected | 1 |

Open questions: 0
Needs review: none
User requirements: 33 (15 approved)
<!-- /trace:status -->
