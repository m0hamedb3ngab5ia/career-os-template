---
name: answer-question
description: Answer one application-form question for a job dir. Uses profile/standard_answers.yaml verbatim when a match pattern hits; drafts essay-style answers in the candidate's voice from profile bullet/narrative ids; refuses (needs_review) legal, sensitive, or freeform salary questions. Appends to answers.json.
---

# answer-question

`$ARGUMENTS` = `<job_dir> "<question text>" [--limit <chars>] [--field-type text|textarea|select] [--options "a|b|c"]`

Parse: first token is `JOB`; the quoted string is `QUESTION`; `--limit` is the character limit (null if
absent); `--options` lists dropdown choices when the field is a select.

## 1. Standard answer lookup (always first)

Read `profile/standard_answers.yaml` (a list of `{key, match[], answer, note?}` plus an `eeo` block).
For each entry in order, test every `match` pattern as a case-insensitive regex (`re.search`) against
`QUESTION`. First hit wins.

- Hit with non-null `answer`: use it VERBATIM. `type: standard`, `needs_review: false`.
  - If `--options` were given, choose the option that equals the answer case-insensitively, else the
    option that contains it; if none, `answer: null`, `needs_review: true`, reason `option_mismatch`.
  - Special keys: `previously_applied` and `referral` have notes about tracker overrides; if
    `JOB/contacts.json` lists a contact with `referrer: true`, answer referral with that name and set
    `needs_review: true` so the candidate confirms.
- Hit with `answer: null` (e.g. `salary_expectation`): `answer: null`, `needs_review: true`,
  `type: standard`, `action_item: "salary_freeform: <question>"`. If `--options` exist, pick the lowest
  bucket whose lower bound >= `config/targets.yaml: candidate.salary_dropdown_floor_usd` (missing key → no pick),
  `needs_review: true`.
- EEO / self-identification questions (gender, race, ethnicity, veteran, disability, Hispanic/Latino):
  use the exact value from the `eeo` block; if the option text differs, `answer: null`, `needs_review: true`.

## 2. Classify when no standard match

- `essay`: "why <company>", "why this role", "tell us about a project", "describe a challenge",
  "what are you proud of", "what interests you", "anything else", "cover letter" text box.
- `sensitive`: legal status beyond standard keys, criminal history, background-check consent wording,
  health/medical, references' contact info, SSN, date of birth, government ID, non-compete specifics
  not covered, "have you signed an agreement with ...", or anything about the current employer's contract terms.
- `salary_freeform`: any pay/compensation question without a standard match.
- `unknown`: everything else (e.g. "Which office?", "Preferred team?", "How did you find us?" variants
  not matched).

For `sensitive`, `salary_freeform`, and `unknown`: `answer: null`, `needs_review: true`,
`type: generated`, `action_item: "<class>: <question>"`. Do not guess.

## 3. Draft an essay answer

Read `profile/master.yaml` (bullets, narratives), `profile/voice/style_guide.md` (+ samples),
`JOB/posting.json`, `JOB/score.json`, and `JOB/cover_letter.md` if present (reuse its facts and ids
so the application is consistent; do not paste the letter).

Rules:
- Only claims traceable to bullet ids / narrative ids; record them in `bullet_ids` / `narrative_ids`.
  Placeholder bullets never. Numbers and tools exactly as in the bullet.
- Company facts only from `posting.json.description_text` or `cover_letter.md` frontmatter `facts_used`.
- Voice: first person, short sentences, no banned phrases (`config/qa.yaml`), <= 2 em-dashes,
  no rhetorical questions. Start with the concrete thing.
- Plain text: answers are pasted into form fields. Bullet text may carry `**bold**` markers (résumé PDF only);
  never copy them: an answer containing `**` hard-fails QA (`no_markdown_bold`).
- Length: <= `--limit` characters if given (leave 5% headroom); else 600-1200 characters. Count.
- "Why us" answers: 1 sourced fact + 1 narrative id + 1 bullet id. "Project" answers: use the bullets
  of the `projects[]` entry whose `tags`/`stack` best match the posting (`config/categories.yaml:
  bullet_priority` for `score.category` breaks ties).
  "Challenge" answers: pick a bullet with a measurable outcome; describe the problem, what the candidate
  did, the result number from the bullet; do not invent obstacles not implied by the bullet text.
- `needs_review`: true if tier A (from score.json), if `voice_verified` would be false and the answer
  is > 400 chars, or if you had to use a project older than 2024 as the main evidence.

## 4. Append to `JOB/answers.json`

`answers.json` is a JSON list. Create it if missing. Append (replace an existing entry with the same
`question`):

```json
{
  "question": "<verbatim>", "answer": "<text or null>", "type": "standard|generated",
  "standard_key": "<key or null>", "class": "standard|essay|sensitive|salary_freeform|unknown",
  "char_limit": 500, "char_count": 468, "field_type": "textarea",
  "bullet_ids": [], "narrative_ids": [], "facts_used": [],
  "needs_review": false, "action_item": null, "answered_at": "<ISO>"
}
```

Append to `JOB/log.md`: `- YYYY-MM-DD HH:MM:SS [answer-question] "<first 60 chars>" type=<t> class=<c> needs_review=<b>`
(format `- YYYY-MM-DD HH:MM:SS [<skill>] <message>`, local time, identical to `store.append_log`; e.g. `date '+%F %T'`).

## 5. RESULT

`RESULT: {"skill":"answer-question","job_id":"...","type":"standard","class":"standard","answer_present":true,"needs_review":false,"char_count":3,"action_item":null}`

When `action_item` is set, RESULT must include `"ACTION_ITEM":"<class>: <question> (limit <n>)"` so the
caller adds it with `careeros action add "<text>" --type question --job <job_id> --priority H`.
