# LinkedIn connection note

Hard limit: 300 characters (LinkedIn truncates silently). `draft-outreach` counts before saving.
Drafts only. The candidate sends every LinkedIn message themselves (Action Item `send_linkedin`).

## Guidance

- One concrete reason for connecting: the role, a shared school, a specific thing they built or wrote.
- One line of proof from `profile/master.yaml`, by bullet id. Numbers, not adjectives.
- No ask beyond "connect". The ask comes after they accept (`linkedin_message.md`).
- No "I'd love to", no "passionate", nothing from `config/qa.yaml: banned_phrases`.
- Address by first name. No "Dear".

## Skeleton

```
Hi <First>, <one-line reason tied to them or the role>. <one line of proof, bullet id>. Would like to connect.
- <Candidate first name>
```

## Examples

EXAMPLE (fictional candidate Alex Example) — regenerate in the candidate's voice once samples exist.

```
Hi Priya, I applied to the Backend SWE role on your team this week. At Acme I built a Kafka-to-PostgreSQL service that handles 2 million events per day. Would like to connect.
- Alex
```
(171 chars; proof: acme.1)

EXAMPLE (fictional candidate Alex Example) — regenerate in the candidate's voice once samples exist.

```
Hi Dan, fellow Springfield State grad. I saw you're on the data platform team at Ledgerline; I spent last summer writing Airflow DAGs and profiling data quality at Initech. Would like to connect.
- Alex
```
(196 chars; proof: initech_intern.1, initech_intern.2; school from education)
