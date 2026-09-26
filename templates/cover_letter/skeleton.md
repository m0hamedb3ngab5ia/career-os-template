# Cover letter skeleton

Structure only. `write-cover-letter` produces `data/jobs/<id>/cover_letter.md` with this frontmatter
and usually four paragraphs. Never copy sentences from here. Source of voice: `profile/voice/style_guide.md`.
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

The candidate's `profile/voice/style_guide.md` may define its own structure and evidence-selection method; if so it
wins over this default. Reference letters in `profile/voice/examples/` show quality and density, never content.

Every letter answers: why this company and role, what the candidate did that is most relevant, what that proves about
them as an engineer, and why that makes them a fit here. Pick 1-2 experiences; do not summarize the résumé.

### 1. Opening (2 to 3 sentences)

Must contain: the role, and something concrete about what the company builds, what problems it solves or who
depends on it (from `company_facts`), connected naturally to the candidate's work.

Forbidden: "I am writing to", "I'm excited", "I came across", "your mission resonates", praise without a fact, any
sentence about the company that could apply to a different company.

### 2. Main experience (3 to 5 sentences)

Must contain: what the system or product was, who depended on it, what the candidate personally built or changed,
production context or a result when useful, and only the technologies that matter to this company. Domain terms are
explained through context. Ends on what the experience demonstrates, not on a technology.

Forbidden: rephrasing a bullet so a number changes or a tool appears that is not in the profile; listing skills as a
comma chain; architecture dumps; tricolons of adjectives.

### 3. Second experience (2 to 4 sentences, optional)

Must contain: something the first paragraph does not show (another project or role, a workflow, leadership), or the
"why this domain" angle taken from `profile/master.yaml: narratives` by id (e.g. `n.data`, `n.builder`).

Forbidden: a second company compliment; inventing motivation not in `narratives`; "passionate".

### 4. Back to the company, then close (2 to 3 sentences)

Must contain: the intersection of what the company needs and what the candidate has shown, earned by the paragraphs
above; then one line from Letter settings `Close variants` (rotated; see write-cover-letter), then the sign-off.

Forbidden: "I believe I would be a great fit", "look forward to hearing from you", thanking them for
their time, restating the résumé.

## Global rules

- First person. Register (contractions, sentence length) follows the style guide. Specific evidence over adjectives.
- Max 2 em dashes in the whole document. No rhetorical questions.
- No word or phrase on `config/qa.yaml: banned_phrases`.
- Company name spelled exactly as in `posting.json`.
- Until `profile/voice/samples/` has real samples, QA marks the letter `voice_unverified`.
