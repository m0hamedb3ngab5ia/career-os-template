# Cold email (engineer or hiring manager)

Sent via Gmail only after the candidate confirms the template (see TODO.md). Until then: draft in Contacts tab.
Target 80 to 130 words. Subject under 60 characters.

## Guidance

- Subject names the role or the thing you have in common. No "Quick question", no "Opportunity".
- First sentence: why them, specifically. A sourced fact about their team or something they wrote.
- Proof: 2 sentences, bullet ids, numbers intact.
- Ask: one. Call, referral, or "who should I talk to".
- Close: "Would like to talk." or similar. Sign with the first name from `profile/master.yaml: identity.name`,
  phone and LinkedIn from `identity` under it.
- Email address confidence must be `verified` or `pattern_match_high` before any auto-send.
- Nothing from `config/qa.yaml: banned_phrases`.

## Skeleton

```
Subject: <Role> at <Company> / <shared thing>

Hi <First>,

<Sourced fact about their team or work, one sentence.> <Why that connects to me, one sentence.>

<Proof 1 (bullet id).> <Proof 2 (bullet id).>

<Single ask.>

<Candidate first name>
<identity.phone> | <identity.linkedin>
```

## Example

EXAMPLE (fictional candidate Alex Example) — regenerate in the candidate's voice once samples exist.

```
Subject: Backend SWE at Ledgerline / settlement pipeline

Hi Dan,

Your post on moving settlement off cron-based reconciliation was the clearest write-up of that problem I've read. I applied to the Backend SWE role on that team on Sep 22.

At Acme I built a FastAPI service that ingests Kafka order events into PostgreSQL, processing 2 million events per day. Before that I wrote 12 Airflow DAGs at Initech that cut manual prep by 5 hours per week.

Is there someone on the team I should talk to about the role? Would like to talk.

Alex
555-010-0199 | linkedin.com/in/alex-example
```
(proof: acme.1, initech_intern.1; fact source: blog URL in Contacts row)
