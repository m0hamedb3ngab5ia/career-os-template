---
name: tailor-resume
description: Build a one-page tailored resume for a scored job dir from profile/master.yaml bullets only (by id). Writes resume.json, resume.txt and resume.tex (via templates/resume/render.py). Never invents metrics or tools.
---

# tailor-resume

`$ARGUMENTS` = job dir (`JOB`). Requires `JOB/posting.json` and `JOB/score.json` (run
`.claude/skills/score-job/SKILL.md` first if score.json is missing).

## Anti-fabrication contract (read twice)

1. Every bullet you output is a profile bullet referenced by `id`. Text is the bullet's `text` verbatim
   or one of its listed `variants`. You may trim a trailing clause or swap a leading verb for a synonym,
   but every number, tool name, and proper noun in the output must already be in that bullet's text.
2. Bullets with `placeholder: true` or text starting `[FILL IN` are never used. If the category's
   `bullet_priority` points to an entry whose bullets are all placeholders, skip that entry and record
   it in `meta.profile_gaps`.
3. Skills section may list only terms from `profile.skills.*` or from the `stack` of an entry you
   included. No new tools, even if the posting wants them.
4. Evidence: follow `.claude/skills/_shared/evidence_rules.md`. Familiarity with a tool needs
   `profile.skills.<key>` or a `stack`; anything with a number or outcome needs a bullet id. Keyword
   mirroring is allowed only under those rules; record each pair in `meta.keyword_mirror`.
5. Summary is one of `profile.summary_variants` verbatim (`general`, `backend`, `data`, `mobile`), or
   null. Do not write a new summary.

## 1. Read

- `JOB/posting.json`, `JOB/score.json` (category, required_skills, matched_skills, skill_evidence).
- `profile/master.yaml`.
- `config/categories.yaml` -> `bullet_priority` for `score.category`, and `resume_template`.
- `config/qa.yaml` -> `resume.hard.section_order`, `resume.soft.keyword_coverage_min`.
- `templates/resume/resume_schema.md` (the JSON shape `render.py` expects) and `templates/resume/<resume_template>.tex`.
  If `resume_schema.md` is absent, use the shape in section 4 below (it is the same shape) and say so in the RESULT.

## 2. Select content (1-page budget)

Budget (measured against `templates/resume/default.tex`, 0.5in margins, 10pt/`\small`): <= 4
experience entries, <= 3 projects, summary + full skills section. <= 14 bullets / <= 550 words in
resume.txt is the safe target; 16 bullets / 600 words sometimes fits (depends on bullet length and
line wraps), and 20 bullets / 608 words spills to 2 pages. The `pdf_page_count` fix loop in section 5
is the source of truth: aim for the safe target, and let the loop decide.

Procedure:
1. Experience entries: include ALL non-placeholder experience entries in reverse-chronological order
   (newest `start` first; entries with `start: null` last) up to the budget of 4, regardless of tag.
   Skip placeholder-only entries (note `profile_gaps`). Tags do not decide inclusion; they decide
   bullet count (step 2) and project selection (step 1b).
   1b. Projects: pick up to 3 by relevance: first projects whose `tags` include `score.category`, then
   projects whose `stack` overlaps `required_skills`, then `bullet_priority` order; ties newest first.
2. Bullet count per entry: tag-matched entries (entry `tags` include `score.category`, or `stack`
   overlaps >= 2 `required_skills`) get 3-4 bullets; other entries get 1-2. Always include at least
   1 bullet per included entry. Choose bullets by: (a) text contains a `required_skills` term (per
   `score.skill_evidence`), (b) has `metrics`, (c) the rest.
   Projects: ALWAYS include the entry's descriptive "what it is" bullet (the one describing the project
   overall; in the example profile, `widgetizer.1`) before any metric bullet, even at a 1-bullet cap.
   Display order within an entry: descriptive bullet first (projects), then by relevance to
   `required_skills`, then metric-only bullets.
3. Education: always every `education[]` entry (most recent first); include `gpa`; include up to 6 `coursework` items, prioritizing ones
   that echo posting terms (e.g. Database Systems, Machine Learning); include `activities` only if the
   budget allows.
4. Skills: reorder each list so terms in `required_skills` come first; drop terms irrelevant to the
   category if over budget (never add). Keep the four keys `programming, frameworks, tools, concepts`.
5. Summary: pick the `profile.summary_variants` key by category:
   - `backend` -> `swe_backend`, `swe_platform`, `quant_dev`, `sre_devops`
   - `data` -> `data_engineering`
   - `mobile` -> `swe_mobile`
   - `general` -> everything else
   Set to null if the budget is exceeded.
6. Section order: exactly `config/qa.yaml: resume.hard.section_order` (the shipped default is
   `experience, projects, education, skills`). No per-category reordering; to lead with a project,
   change that config value. Summary, when present, is first.
7. Dates: display strings `Mon YYYY` (e.g. `Jun 2025`), `Present` for open-ended. Convert from
   the profile's `YYYY-MM`.

## 3. Keyword coverage check (before writing)

Compute `coverage = |required_skills that appear in your chosen bullet texts + skills lists| / |required_skills|`.
If below `keyword_coverage_min` (0.6), look for additional profile evidence for the missing terms and
swap bullets; if none exists, proceed and list `missing_terms` in `meta` (QA will soft-warn). Never
add a term without evidence.

## 4. Write `JOB/resume.json`

Exactly the shape in `templates/resume/resume_schema.md`: `identity` (copied from profile),
`summary`, `sections[{type, order}]`, `experience[]` (id, company, title, team, location, start, end,
`bullets[{id, text}]`), `projects[]` (id, name, date, stack (subset of profile stack), link,
`bullets[{id, text}]`), `education[]`, `skills{}`, and `meta`:

```json
"meta": {
  "job_id": "...", "category": "swe_backend", "resume_version": "swe_backend-v1", "template": "default",
  "bullet_ids": ["initech_intern.1", "..."],
  "keyword_mirror": {"ETL pipelines": "initech_intern.1", "AWS": "skills.tools", "SQL": "initech_intern.2"},
  "required_skills_covered": ["Python", "SQL", "AWS"], "missing_terms": ["Go", "Kafka"],
  "coverage": 0.71, "profile_gaps": ["acme.4: placeholder bullet skipped"],
  "word_count_estimate": 520, "dropped_for_fit": []
}
```
`keyword_mirror` values are the bullet id or `skills.<key>` that justifies using that posting term.
`resume_version` = `<category>-v<n>` where n increments if a resume.json for this job already existed.

## 5. Render

Run: `.venv/bin/python templates/resume/render.py JOB/resume.json`
- This writes `resume.tex` and `resume.txt` (and `resume.pdf` only if a LaTeX engine is installed; a
  missing engine is a warning, not a failure). If `render.py` is missing, write `resume.txt` yourself
  in the "Plain-text render order" described in `resume_schema.md` (header line, contact line, SUMMARY,
  then sections; bullets prefixed `- `) and skip `.tex`.
- If render.py errors on placeholders, you used a placeholder bullet: fix resume.json and rerun.

Then run `.venv/bin/python -m careeros.qa JOB` and read `checks`. If `truth_trace`, `number_audit:resume.txt`,
`tool_audit`, or `contact_intact:resume.txt` fails, fix resume.json (remove the offending bullet/term;
never edit a number to make it pass) and re-render. Max 2 fix loops; then leave it and report.

`pdf_page_count` fix loop (only when `resume.pdf` was built): if the check reports 2 pages, apply
the first applicable step below, re-render, re-run QA, and repeat until 1 page. Record every swap or
drop in `meta.dropped_for_fit`. Invariants at every step: never drop a project's descriptive bullet,
never drop an entry's last bullet (entries stay at >= 1 bullet), never drop an entry.

1. Short-variant swap: if any included bullet has `variants.short` in the profile and the long text
   is in use, swap it to the short variant (least relevant bullet first). This is a fit step, not a
   drop, and comes before removing any bullet.
2. Non-tag-matched entries: drop the lowest-relevance bullet of the least relevant non-tag-matched
   entry, until every non-tag-matched entry is at 1 bullet.
3. Tag-matched entries: only once all non-tag-matched entries are at 1 bullet, drop the
   lowest-relevance bullet from a tag-matched entry (lowest relevance to `required_skills`, metric-only
   bullets last), one at a time, until each tag-matched entry is at its minimum (1 bullet; for
   projects, the descriptive bullet).
4. Only then: drop `education.activities`, then trim `coursework` to 4, then set `summary` to null.

## 6. Log and RESULT

Append to `JOB/log.md`: `- YYYY-MM-DD HH:MM:SS [tailor-resume] version=<resume_version> bullets=<n> words=<n> pages=<n> coverage=<x> gaps=<...>`
(format `- YYYY-MM-DD HH:MM:SS [<skill>] <message>`, local time, identical to `store.append_log`; e.g. `date '+%F %T'`).

Last line:
`RESULT: {"skill":"tailor-resume","job_id":"...","resume_version":"swe_backend-v1","bullets":11,"words":520,"pages":1,"coverage":0.71,"missing_terms":["Go","Kafka"],"profile_gaps":["acme.4"],"files":["resume.json","resume.txt","resume.tex"],"qa_hard_fails":[],"schema_source":"resume_schema.md"}`
