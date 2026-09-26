---
name: write-cover-letter
description: Write a cover letter (length from config/qa.yaml) for a scored job dir in the candidate's voice, using only profile bullets/narratives by id and at least two sourced company facts. Writes cover_letter.md with YAML frontmatter for QA.
---

# write-cover-letter

`$ARGUMENTS` = job dir (`JOB`), optionally followed by `--suggestions "<text>"` (regeneration hints from
qa-review). Requires `JOB/posting.json` and `JOB/score.json`; uses `JOB/resume.json` if present so the
letter and resume tell the same story.

## Anti-fabrication contract

- Every claim about the candidate traces to a bullet id (`experience[].bullets[].id`, `projects[].bullets[].id`,
  `leadership[].bullets[].id`) or a narrative id (`narratives[].id`) in `profile/master.yaml`.
  Placeholder bullets (`placeholder: true` / `[FILL IN`) are never cited or paraphrased.
- Numbers appear exactly as in the cited bullet (`2 million events per day`, `40 analysts`, `12 Airflow DAGs`).
  Do not round, combine, or extrapolate ("hundreds of PRs" is fine only if you also don't state a number;
  prefer the exact number).
- Evidence rules: `.claude/skills/_shared/evidence_rules.md`. Saying you know/have used a tool needs
  `profile.skills.<key>` or an entry `stack`; any number or outcome needs a bullet id. Do not claim
  experience with a posting technology that the profile lacks. It is fine to say you have not used X
  and that Y is the closest thing you have done.
- Motivation claims ("why finance", "why AI tooling") come only from `narratives`.
- Every company/team fact comes from `posting.json.description_text` (source `posting`) or a page you
  fetched with WebFetch (source = the URL). If WebFetch is unavailable or fails, use posting facts only.
  Never state a company fact from memory.

## 1. Read

1. `JOB/posting.json`, `JOB/score.json` (category, tier, required_skills, matched_skills, skill_evidence).
2. `profile/master.yaml` (bullets, narratives, summary_variants, identity).
3. `profile/voice/style_guide.md`: its `## Letter settings` (Greeting, Sign-off, Length, Close variants),
   Rules, Cover-letter skeleton, and `## Learned` if filled; and every file in `profile/voice/samples/`.
   If `samples/` is empty, the letter is `voice_verified: false`.
   Also every file in `profile/voice/examples/` if present: approved reference letters. Copy their quality,
   structure and density, never their content (experiences, technologies, themes). When the style guide
   describes a letter structure or evidence-selection method, it overrides the defaults in steps 3-4 below.
   Previous closes: the `close_variant` frontmatter of every `data/jobs/*/cover_letter.md` (note the most
   recent one by `date`, and every one whose `company` is this company).
4. `templates/cover_letter/skeleton.md` if present (frontmatter keys expected by its renderer).
5. `config/qa.yaml`: `banned_phrases`, `style_rules`, `cover_letter.min_words/max_words`.
6. `config/targets.yaml` tiers: if tier C and `cover_letter: if_required`, and the posting does not
   require a cover letter, stop and print `RESULT: {"skill":"write-cover-letter","job_id":"...","skipped":"tier_c_not_required"}`.

## 2. Collect company facts (need >= 2)

From `description_text`: extract concrete, checkable facts about the company or the team (what the
team owns, a system named, scale numbers, office, program, product). Generic mission statements do
not count. If fewer than 2 concrete facts exist in the posting and WebFetch is available, fetch the
company homepage or `/about`/engineering blog (max 2 fetches) and take facts from there, citing the URL.
If still fewer than 2: write the letter with what you have and set `facts_shortfall: true` (QA will fail
`company_facts_min`; the caller creates an Action Item).

## 3. Plan (internal; do not print the plan)

Every letter answers: why this company and role; what the candidate has done that is most relevant; what that
proves about them as an engineer; why that makes them a fit for this company. It is not a résumé summary.

Before drafting, decide:
1. What the company actually builds, what engineering problems it solves, who depends on it (from the facts in step 2).
2. Which qualities the posting emphasizes (`score.skill_evidence`, requirements, "who you are" text).
3. The 1-2 experiences (bullet ids or narrative ids) that are the strongest evidence for those qualities. Choose from
   the whole profile, not the most recent job by default; the style guide may list defaults per company type.
   Prefer bullets already in `JOB/resume.json` so the story is consistent.
4. Which experience makes the most natural opening connection to what the company builds.
5. Which technologies are worth naming for this company (only those that strengthen the story) and which details to drop.
6. What each paragraph proves.

## 4. Draft (default structure; the style guide's structure wins if it has one)

Greeting: the style guide's `Greeting:` line, with its placeholders filled. If the guide has none, use
`Hi <Team> team,` when a real team name is known, else the company form. Never `Dear Hiring Manager`
(also a banned phrase). A `departments` value is a team name only if it reads like one (e.g. "Payments Infrastructure",
"Developer Platform"). Values that look like ATS buckets are NOT team names: anything containing a
digit, or matching `/general|university|early careers|campus|other/i` (e.g. "University 2026",
"Early Careers", "General", "Other") -> use the company form and set `team: null`.

1. Opening (2-3 sentences): name the role exactly as in posting.json (title may be shortened to its core) and say
   something concrete about what the company builds and who depends on it, then the natural connection to the
   candidate's work. No generic praise ("innovative culture", "mission resonates").
2. Main experience (3-5 sentences): what system or product, who depended on it, what the candidate personally worked
   on, what they built or changed, production context or scale or a result when useful, a few relevant technologies.
   Explain domain terms through context for a reader outside the field. End on what the experience demonstrates
   (reliability, ownership, production engineering, ...), not on a technology.
3. Second experience (2-4 sentences, optional): adds something the first does not (a project, another role, a
   workflow, leadership), or the "why this domain" angle from a narrative. Skip it if another shape is stronger.
4. Back to the company + close (2-3 sentences): the intersection of what the company needs, what the candidate has
   shown, and the work they want to keep doing; it must feel earned by the paragraphs above. Then one line from the
   style guide's `Close variants:`. Pick a variant that is neither the most recent letter's `close_variant` nor any
   `close_variant` already sent to this company (QA soft-warns `close_variant_repeated`). If every variant was used for
   this company, pick the least recently used. Record it as `close_variant`. No variants listed -> a plain ask in the
   same spirit. Sign-off: the style guide's `Sign-off:` line (default: first name from `profile/master.yaml: identity.name`).

Voice: the style guide's rules decide register (contractions, sentence length). Hard in every case: first person,
specific evidence instead of adjectives, no stack dump (never a bare comma list of tools), no throat-clearing openers
("I had the opportunity to", "I was fortunate enough to"), no praise beyond the sourced facts, <= 2 em-dashes, no
rhetorical questions, no tricolon of adjectives, none of `banned_phrases` (case-insensitive, including
"leverage"/"dynamic"/"thrilled"). If `--suggestions` were passed, apply them without violating any rule above.

Plain prose: profile bullet text may carry `**bold**` markers around tech names and metrics (they are for the résumé
PDF only). Never copy them into the letter: write "2 million events per day", not "**2 million events per day**".
QA hard-fails a stray `**` in the body (`no_markdown_bold`, it would print literally) and soft-warns any bold
(`cover_letter_bold`).

Length: `config/qa.yaml: cover_letter.min_words` to `cover_letter.max_words` words in the body (greeting
through sign-off); the style guide's `Length:` line points there. QA computes the count itself
(`cover_letter_word_count` in `careeros.qa` output); your own count is only a guide.

## 5. Write `JOB/cover_letter.md`

```markdown
---
job_id: <job_id>
company: <exact company>
role: <exact title>
team: <team or null>
greeting: "<greeting from the style guide>"
date: <YYYY-MM-DD>
sign_off: "<Sign-off from the style guide>"
close_variant: "<the Close variant used, verbatim>"
word_count: <int, body only; optional/informational. QA computes the real count and never fails on a mismatch>
facts_used:
  - {fact: "<fact as used>", source: posting}
  - {fact: "<fact>", source: "https://..."}
company_facts: <same list as facts_used>
bullet_ids_used: [acme.1, initech_intern.1]
narrative_ids_used: [n.data]
bullet_ids: <same as bullet_ids_used>
narrative_ids: <same as narrative_ids_used>
voice_verified: <true only if profile/voice/samples/ has >= 1 file AND style_guide "## Learned" is filled>
facts_shortfall: false
regeneration: <0, or n if rewritten after qa-review>
---
<greeting>

<body paragraphs separated by blank lines; the last one ends with the close_variant>

<sign_off>
```
(The duplicated keys keep both `templates/cover_letter/render.py` and `careeros.qa` happy.)

## 6. Self-check, then log

Run `.venv/bin/python -m careeros.qa JOB`. If `banned_phrases`, `cover_letter_word_count`,
`number_audit:cover_letter.md`, `truth_trace`, `cover_letter_names_company/role`, or
`cover_letter_company_facts` fails, fix and rewrite once. Do not loosen a number to pass.

Append to `JOB/log.md`: `- YYYY-MM-DD HH:MM:SS [write-cover-letter] words=<n> facts=<n> bullets=<ids> narratives=<ids> voice_verified=<bool> regeneration=<n>`
(format `- YYYY-MM-DD HH:MM:SS [<skill>] <message>`, local time, identical to `store.append_log`; e.g. `date '+%F %T'`). `words` = the `cover_letter_word_count` reported by QA.

Last line:
`RESULT: {"skill":"write-cover-letter","job_id":"...","word_count":181,"facts":2,"bullet_ids":["..."],"narrative_ids":["..."],"voice_verified":false,"facts_shortfall":false,"qa_hard_fails":[]}`
