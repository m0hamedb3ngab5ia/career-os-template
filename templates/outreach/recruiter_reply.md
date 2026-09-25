# Reply to inbound recruiter message

For messages from recruiters (LinkedIn or email) about a role. Draft only; the candidate sends.
50 to 100 words. Answer every question they asked, in order.

## Guidance

- Say yes or no to interest in the first sentence. Don't make them read to the end.
- If yes: give availability in concrete slots (weekday, time window, the candidate's timezone).
- If they asked for salary: do not answer with a number. Use `profile/standard_answers.yaml` rule:
  freeform salary is an Action Item. Draft says "happy to discuss once I understand the level and scope".
- If they asked for work authorization / sponsorship: answers from `standard_answers.yaml` only
  (`work_authorization`, `sponsorship`, `citizenship`), verbatim.
- Attach the current résumé PDF only if they asked; use the general version, not a tailored one.
- If no: one sentence, keep it warm, ask to stay in touch.
- Nothing from `config/qa.yaml: banned_phrases`.

## Skeleton

```
Hi <First>,

<Yes/no + role name.> <Answers to their questions, in order, one sentence each.>

<Availability slots, with timezone.> <Résumé attached, if asked.>

<Candidate first name>
<identity.phone>
```

## Example

EXAMPLE (fictional candidate Alex Example) — regenerate in the candidate's voice once samples exist.

```
Hi Sarah,

Yes, interested in the Data Engineer role. I'm a US citizen and don't need sponsorship. Comp I'd rather discuss once I understand the level and scope.

I'm free Tuesday 12 to 2pm ET or Thursday after 4pm ET. Résumé attached.

Alex
555-010-0199
```
