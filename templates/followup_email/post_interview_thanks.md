# Thank-you email, same day as an interview

Sent within 6 hours of the interview, to each interviewer whose email is known (else via recruiter).
60 to 110 words. Subject: "Thanks, <First>" or "<Role> interview today".

## Guidance

- Reference one specific thing from the conversation (a problem they described, a question that
  was hard, something they said about the team). Pulled from the interview notes in the job's `log.md`.
- If a question went badly, one sentence with the better answer. No excuses.
- Restate interest in one plain sentence. Don't oversell.
- No "It was a pleasure", no "I'm confident I", nothing from `config/qa.yaml: banned_phrases`.
- Sign with the candidate's first name. No phone signature needed; they have it.

## Skeleton

```
Subject: <Role> interview today

Hi <First>,

Thanks for the time today. <The specific thing from the conversation, one or two sentences.>

<Optional: better answer to the hard question, one sentence.>

<Plain interest sentence.> <What happens next, if known.>

<Candidate first name>
```

## Example

EXAMPLE (fictional candidate Alex Example) — regenerate in the candidate's voice once samples exist.

```
Subject: Backend SWE interview today

Hi Priya,

Thanks for the time today. The discussion around retried settlement writes stuck with me; it is close to the FastAPI service I built at Acme that ingests Kafka order events into PostgreSQL, 2 million a day.

On the partitioning question, I should have said: partition by merchant, not by date, since the hot path is per-merchant reads.

I'd like to work on this. Happy to do a follow-up round whenever it suits the team.

Alex
```
(proof: acme.1; interview detail from log.md)
