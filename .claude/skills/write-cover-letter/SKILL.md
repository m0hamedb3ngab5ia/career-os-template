---
name: write-cover-letter
description: Write a 120-250 word cover letter for a scored job dir in the candidate's voice, using only profile bullets/narratives by id and at least two sourced company facts. Writes cover_letter.md with YAML frontmatter for QA.
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
3. `profile/voice/style_guide.md` (Rules, Cover-letter skeleton, and `## Learned` if filled) and every
   file in `profile/voice/samples/`. If `samples/` is empty, the letter is `voice_verified: false`.
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

## 3. Choose evidence

- Requirement #1 = the posting's most emphasized requirement that the profile can match
  (use `score.skill_evidence`). Pick 1-2 bullet ids as Proof A.
- Requirement #2 or domain angle: 1 bullet id or 1 narrative id as Proof B. Pick the `narratives[]`
  entry whose text fits the company's domain (e.g. the example's `n.data` for data-heavy teams, `n.builder`
  for early-stage/ownership roles); never write motivation that is not in a narrative.
- Prefer bullets already in `JOB/resume.json` so the story is consistent.

## 4. Draft (follow the skeleton in style_guide.md)

Greeting: `Hi <Team> team,` only when a real team name is known, else `Hi <Company> team,`.
A `departments` value is a team name only if it reads like one (e.g. "Payments Infrastructure",
"Developer Platform"). Values that look like ATS buckets are NOT team names: anything containing a
digit, or matching `/general|university|early careers|campus|other/i` (e.g. "University 2026",
"Early Careers", "General", "Other") -> use `Hi <Company> team,` and set `team: null`.
Never `Dear Hiring Manager`.

1. Hook (1-2 sentences): one sourced fact + the one thing the candidate did that connects. Name the role and
   company exactly as in posting.json (title may be shortened to its core, e.g. "Software Engineer, Backend").
2. Proof A (3-4 sentences): "I did X, result Y" with exact numbers from cited bullets.
3. Proof B (2-3 sentences): requirement #2 or narrative angle; tie back to the hook fact.
4. Close (1-2 sentences): plain ask ("Happy to walk through the code." / "Would like to talk."). Sign with the first name from `profile/master.yaml: identity.name`.

Voice rules (hard): first person, short sentences, one idea each, contractions ok, no throat-clearing
openers, no praise beyond the sourced facts, <= 2 em-dashes, no rhetorical questions, no tricolon of
adjectives, none of `banned_phrases` (case-insensitive, including "leverage"/"dynamic"/"thrilled").
If `--suggestions` were passed, apply them without violating any rule above.

Length: 120-250 words in the body (greeting through sign-off). QA computes the count itself
(`cover_letter_word_count` in `careeros.qa` output); your own count is only a guide.

## 5. Write `JOB/cover_letter.md`

```markdown
---
job_id: <job_id>
company: <exact company>
role: <exact title>
team: <team or null>
greeting: "Hi <Team> team,"
date: <YYYY-MM-DD>
sign_off: "<first name from identity.name>"
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
Hi <Team> team,

<body paragraphs separated by blank lines>

<first name>
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
