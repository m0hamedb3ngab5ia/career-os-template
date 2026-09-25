# Cover letter skeleton

Structure only. `write-cover-letter` produces `data/jobs/<id>/cover_letter.md` with this frontmatter
and four paragraphs. Never copy sentences from here. Source of voice: `profile/voice/style_guide.md`.
Source of facts: `profile/master.yaml` (bullet ids) and `posting.json`. Nothing else.

Length, greeting, sign-off and close variants come from the candidate's files, never from this skeleton:
`profile/voice/style_guide.md` → `## Letter settings` (Greeting, Sign-off, Close variants) and
`config/qa.yaml: cover_letter.min_words` / `max_words` (the Length line points there).

## Frontmatter (required by `render.py`)

```yaml
---
job_id: a1b2c3d4e5f6
company: Acme
role: Software Engineer, Backend
team: Payments Infrastructure      # null if unknown
greeting: "<Greeting from Letter settings, placeholders filled>"
date: 2026-09-24
sign_off: "<Sign-off from Letter settings>"
close_variant: "<the Close variant used, verbatim>"
bullet_ids: [acme.1, initech_intern.1, widgetizer.1]   # every claim below traces here
narrative_ids: [n.data]
company_facts:                      # min 2, each with a source URL or "posting"
  - {fact: "Payments Infra owns the ledger service that settles 40M tx/day", source: posting}
  - {fact: "Engineering blog post on migrating to Rust", source: https://acme.com/blog/...}
---
```

## Body

### 1. Hook (1 to 2 sentences)

Must contain: one concrete, sourced fact about this role or team (from `company_facts`) and the one
thing the candidate actually did that connects to it. Name the role and company in plain words.

Forbidden: "I am writing to", "I'm excited", "I came across", praise without a fact, any sentence
about the company that could apply to a different company.

### 2. Proof A (3 to 4 sentences)

Must contain: the strongest match for the posting's requirement #1, told as "I built X because Y,
result Z" using the numbers from the cited bullet ids exactly. Numbers over adjectives.

Forbidden: rephrasing a bullet so a number changes or a tool appears that is not in the profile;
listing skills as a comma chain; tricolons of adjectives.

### 3. Proof B (2 to 3 sentences)

Must contain: either the match for requirement #2, or the "why this domain" angle taken from
`profile/master.yaml: narratives` by id (e.g. `n.data`, `n.builder`). Ties back to the hook fact.

Forbidden: a second company compliment; inventing motivation not in `narratives`; "passionate".

### 4. Close (1 to 2 sentences)

Must contain: one line from Letter settings `Close variants` (rotated; see write-cover-letter), then the sign-off.

Forbidden: "I believe I would be a great fit", "look forward to hearing from you", thanking them for
their time, restating the résumé.

## Global rules

- First person, short sentences, one idea each. Contractions fine.
- Max 2 em dashes in the whole document. No rhetorical questions.
- No word or phrase on `config/qa.yaml: banned_phrases`.
- Company name spelled exactly as in `posting.json`.
- Until `profile/voice/samples/` has real samples, QA marks the letter `voice_unverified`.
