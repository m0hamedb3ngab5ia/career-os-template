# Status

## Now
- Lane: Feature — onboarding + profile (USR-002..004, 022..027) + injection guard, résumé reuse, check a job (USR-033, 031, 028)
- Stage: Build. TASK-001..023 and TASK-025 shipped (#115..#150); private UI ported to the template (#156). Specs/IA/arch approved 2026-10-04 (see Gates)
- Done: REQ-093..116, UC-001..012, FLOW-001/002 approved (gates 2026-10-04)
- Next: résumé workspace (REQ-124..126, DEC-012..019): arch delta merged #168; TASK-027..033 written (supersede TASK-024) → build TASK-027 first; stream ttv-user-test, TASK-026 (Action Items in data/action_items.json)
- Waiting on user: audit triage gate; other USR triage. merge #166. Later: Q-008 json, USR-029/030/032

## Gates
| gate | status | date |
|---|---|---|
| Audit triage | pending | |
| Onboarding+profile spec (Feature) | approved | 2026-10-04 |
| Résumé workspace spec (Feature, DEC-012) | approved | 2026-10-12 |
| Injection guard + résumé reuse + check-a-job spec (Feature) | approved | 2026-10-04 |
| Architecture delta (DEC-001..008, REQ-108 tools amended) | approved | 2026-10-04 |
| IA + UI (06_IA.md, 08_DESIGN_SYSTEM.md, mockups, DEC-009) | approved | 2026-10-04 |
| Pipeline start + guidance + tour spec (USR-034..037: REQ-117..122, UC-013/014, TASK-016..020) | approved | 2026-10-04 |

## Deletion candidates
<!-- rejected REQs whose code still exists -->
- REQ-062 Gmail auto-send: check any send path in inbox/outreach code; `qa_ext` `email_autosend_verified` stays as guard

## Trace
<!-- trace:status -->
| REQ status | n |
|---|---|
| approved | 31 |
| proposed | 61 |
| rejected | 1 |

Open questions: 0
Needs review: none
User requirements: 37 (19 approved)
<!-- /trace:status -->
