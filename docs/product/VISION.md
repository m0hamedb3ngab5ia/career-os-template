# Vision
Reconstructed by `/product audit` 2026-10-04 from README.md, ARCHITECTURE.md, docs/UI.md, TODO.md, .agent/DECISIONS.md.
Tags: `(observed)` in code/docs · `(inferred)` reading between lines · `(contradictory)` sources disagree · `(decision-needed)`.

## User
- One job seeker ("the candidate"), technical enough to run a CLI + Claude Code on a Mac. (observed: README.md:3, ARCHITECTURE.md:3)
- Secondary: other job seekers who clone the public template with their own private data. (observed: README.md:7, DECISIONS "Personal data lives outside")
- Audience size/skill for template users beyond the owner: (decision-needed, Q-001)

## Problem
- High-volume job search = repetitive: find postings, judge fit, tailor résumé/letter, fill forms, track replies. (inferred)
- Tailoring by LLM risks fabricated facts, wrong company names, leaked employer secrets. (observed: ARCHITECTURE.md:8,16, qa_ext)
- Scam / data-harvesting postings and ghost jobs waste effort and risk PII. (observed: TODO.md "Safety", "Ghost jobs")

## Today's workaround
Manual: boards in browser, résumé edits by hand, spreadsheet tracker. (inferred)

## Desired outcome
- Pipeline runs unattended overnight up to "queued / needs_review"; candidate spends attention only on review + submit + Action Items. (observed: ARCHITECTURE.md:66-68)
- Every claim traces to `profile/master.yaml`; zero fabrication. (observed: ARCHITECTURE.md:8)
- One local app replaces xlsx + CLI + reading JSON. (observed: docs/UI.md:13-21)
- System learns: a question answered once is never asked again. (observed: ARCHITECTURE.md:256-257)

## Value
Volume + quality at once: more tailored applications per week without fabrication or scam exposure. (inferred)

## Success metrics
- None defined in repo. Candidates: applications/week, QA first-pass rate, interview rate by tier, minutes of candidate time per application. (decision-needed, Q-002)
- TODO "Weekly self-review report" hints at acceptance rate by category/tier, QA fail reasons, time saved. (observed: TODO.md:39)

## Assumptions
- A-01 Claude Code subscription is enough for all LLM work (no API key). — test: run budgets vs usage limits. (observed: DECISIONS)
- A-02 Greenhouse/Lever/Ashby public APIs cover most target postings. — test: share of tracked jobs per ATS. (inferred)
- A-03 Candidate stays logged in on a Mac for scheduled runs (LaunchAgent). (observed: ARCHITECTURE.md:217-218)

## Not goals
- No LinkedIn automation; drafts only. (observed: CLAUDE.md hard rules)
- No Anthropic API key / hosted backend. (observed)
- No multi-user / multi-candidate per install. (inferred, Q-001)
- No LAN / remote access until real auth + TLS. (observed: TODO.md:50)
