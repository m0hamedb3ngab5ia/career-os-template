---
name: draft-outreach
description: Draft (never send) per-contact outreach for a job dir from contacts.json: LinkedIn connection note (<=300 chars), LinkedIn message, cold email subject+body, and 7-day/14-day follow-ups, in the candidate's voice using only profile bullet/narrative ids. Writes outreach.json.
---

# draft-outreach

`$ARGUMENTS` = job dir (`JOB`). Requires `JOB/contacts.json` (run `.claude/skills/find-contacts/SKILL.md`
first). This skill writes drafts only. It never sends, never creates Gmail drafts, never opens LinkedIn.

## 1. Read

- `JOB/contacts.json`, `JOB/posting.json`, `JOB/score.json` (tier; tier C -> stop with
  `RESULT: {"skill":"draft-outreach","job_id":"...","skipped":"tier_c_no_outreach"}`).
- `JOB/cover_letter.md` frontmatter `facts_used`/`bullet_ids_used` if present (reuse the same fact and
  proof so all touchpoints agree).
- `profile/master.yaml` (bullets, narratives, identity), `profile/voice/style_guide.md` (+ samples).
- `config/qa.yaml` banned phrases.
- `templates/outreach/*.md` if present: `linkedin_note.md`, `linkedin_message.md`, `cold_email.md`,
  `followup_7d.md`, `followup_14d.md`. Treat each as structure + length guidance, not text to copy. If a
  template is missing, use the structure below and set `templates_used` accordingly.

## 2. Rules

- Every claim traces to a bullet id or narrative id; numbers and tools exactly as in the bullet.
  Placeholder bullets never. Record `bullet_ids` / `narrative_ids` per draft.
- One company/team fact per message, from `contacts.json`/posting/cover letter facts (source recorded).
- Voice: first person, short sentences, plain ask, no flattery, no banned phrases, no em-dash > 1 per
  message, no rhetorical questions, no "I hope this finds you well".
- Never claim a referral, a mutual contact, or that you were told to reach out. Never mention having
  guessed the email.
- Use the contact's first name only if `confidence` is `high`; else open with "Hi," (no name).
- Addressing by role: recruiter -> ask about process/timeline and offer the resume; hiring manager
  -> one proof + one question about the team's system; team lead -> a specific technical question or
  comment on their blog post/system + a light ask.

## 3. Draft per contact

For each entry in `contacts.json.contacts` produce:

1. `linkedin_note` (<= 300 characters including spaces; count precisely): who + one proof + why this
   team + "would like to connect". No links.
2. `linkedin_message` (60-120 words): after connecting. Fact about their team, one proof with a
   number, the ask (15-min chat or "would you be the right person to ask about <role>?").
3. `email`: `subject` (<= 60 chars, e.g. "New grad backend applicant: <role> at <company>"), `body`
   (90-150 words): greeting per rule above, hook fact, proof (bullet ids), ask, sign-off
   `identity.name` + phone + LinkedIn URL from `profile/master.yaml: identity`. `to` = `contact.email` if verified else
   the first `email_candidates` entry with `to_confidence` copied from `email_confidence`.
4. `followup_7d` (40-70 words): reference the original message, add one new proof or fact, repeat the ask once.
5. `followup_14d` (30-50 words): final, polite close-the-loop, leaves the door open. No guilt.

## 4. Write `JOB/outreach.json`

```json
{
  "job_id": "...", "company": "...", "drafted_at": "<ISO>", "templates_used": ["linkedin_note.md", "..."] ,
  "drafts": [
    {"contact": "Jane Doe", "role": "recruiter", "linkedin": "...", "to": "jane.doe@x.com", "to_confidence": "low",
     "linkedin_note": "...", "linkedin_note_chars": 287,
     "linkedin_message": "...", "email": {"subject": "...", "body": "..."},
     "followup_7d": "...", "followup_14d": "...",
     "bullet_ids": ["acme.1"], "narrative_ids": ["n.data"], "facts_used": [{"fact": "...", "source": "posting"}],
     "send_after": null, "sent": false}
  ],
  "review_required": true
}
```
`review_required` is always true for tier A, and true for tier B until the user confirms a template
(`TODO.md`: "Confirm follow-up email template"). Set `send_after` null; the follow-up scheduler fills it.

Append to `JOB/log.md`: `- YYYY-MM-DD HH:MM:SS [draft-outreach] <n> contacts drafted, templates=<list>`
(format `- YYYY-MM-DD HH:MM:SS [<skill>] <message>`, local time, identical to `store.append_log`; e.g. `date '+%F %T'`).

## 5. RESULT

`RESULT: {"skill":"draft-outreach","job_id":"...","drafts":2,"review_required":true,"templates_used":["..."],"ACTION_ITEM":"Review outreach drafts in data/jobs/<id>/outreach.json before sending"}`
