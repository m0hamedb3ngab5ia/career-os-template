---
name: prepare-job
description: Orchestrate full preparation of one job dir: score-job, then (if decision=prepare) tailor-resume, write-cover-letter per tier rule, qa-review with one regeneration cycle. Prints a final RESULT with status queued | needs_review | skipped and any ACTION_ITEMs.
---

# prepare-job

`$ARGUMENTS` = job dir (`JOB`), optional `--force` (re-prepare even if qa.json says pass).

Skills cannot call each other programmatically. For each step, open the named SKILL.md, follow it
inline exactly as written (same inputs, same output files, same RESULT line), then continue here. Keep
each step's RESULT JSON in memory; you will summarize them at the end.

Before starting, read `config/targets.yaml` (tiers, thresholds) and `config/qa.yaml` (`critic.max_regenerations`).
Initialize `action_items = []`, `steps = {}`.

## Step 0: setup guard (fake-data guard)

Run `.venv/bin/careeros doctor --quiet` first. If it exits nonzero, STOP: do not score, tailor or write
anything. Print its FAIL lines, then the final RESULT with `status: skipped`, `skip_reason: "setup: careeros doctor failed"`
and `ACTION_ITEMS: ["setup: fix the careeros doctor FAIL lines (profile still has example data or a tool is missing)"]`.
This keeps the fictional example candidate (Alex Example) out of every real application.

Pruned guard: if `JOB/posting.json` has `pruned: true` (retention cut the description to a preview), STOP:
print the final RESULT with `status: skipped`, `skip_reason: "posting pruned by retention"`. Never score,
tailor or safety-check a stub.

Re-run guard: if `JOB/prepare.json` exists with `qa_pass: true` and `--force` was not given, print its
RESULT again (status unchanged) and stop. `--force` re-prepares from Step 1.

## Step 1: score

Follow `.claude/skills/score-job/SKILL.md` with `JOB`. Store its RESULT as `steps.score`. (Batch phase 2,
below: `JOB/score.json` from phase 1 is the score; use it instead of scoring again.)
- If it errored: final status `skipped`, reason `score_error`, go to Finish.
- If `decision == "skip"` with `skip_reason` `company_cap` or `cooldown`: a gate deferral, not a verdict
  (the gate may have run before other jobs at the company were scored). Go to Step 1b and let the gate
  decide; on exit 0 rewrite `JOB/score.json` with `decision: "prepare"`, `skip_reason: null`.
- If `decision == "skip"` for any other reason: final status `skipped`, reason = `skip_reason` (or first hard filter). Go to Finish.
- If `profile_gap` is set: `action_items.append("profile_gap: " + profile_gap)` (priority M, once per gap).

`tier` = score.tier. `tier_cfg` = `targets.tiers[tier]` (tier null -> treat as C).

## Step 1b: company gate (before any tailoring)

Run `.venv/bin/careeros company gate <job_id> --json` again (score-job ran it; a rejection or a new
reservation may have landed since, and a re-run with `--force` skips nothing). Keep its JSON as `gate`.
- Exit 3: final status `skipped`, reason = `gate.reason` (`company_cap`, `cooldown`, `not_similar`,
  `closed`). Record it with `--note "<gate.reason>: <gate.detail>"` (the note must start with the reason:
  score.json may still say `prepare`, and the note is how the gate and `requeue` know this is a deferral). Go to Finish. `company_cap` / `cooldown` are deferred, not dropped:
  `careeros company requeue` sets them back to `scored` once a slot opens or the cooldown ends.
- Exit 0: continue. If `gate.urgent`, this job goes first (a close date before the cooldown ends, or a
  cluster of similar roles at the company closing together): every Action Item for it below gets
  `gate.action_note` appended and priority H, and run
  `.venv/bin/careeros tracker upsert <job_id> --field NextActionDate=<gate.closes_at>` when `closes_at` is set.

Batches run in two phases, so the gate ranks every candidate by fit before any slot is reserved (scoring
and preparing one job at a time would let a lower-fit job reserved first beat a higher-fit one found later):
- Phase 1: follow `.claude/skills/score-job/SKILL.md` (gate included) for every job in
  `careeros jobs list --status found`. Prepare nothing yet.
- Phase 2: for each job in `careeros jobs list --status found --status scored --order urgent` order (urgent
  first, then the earliest close date, then fit; `scored` = requeued deferrals), re-run
  `careeros company gate <job_id> --json` right before preparing it: exit 0 -> run this skill on it
  (Step 1 reuses the phase 1 `score.json`: do not re-score); exit 3 -> record it as in Step 1b and move on.
  A job prepared earlier in the phase holds its slot, so the ranking stays correct as slots fill.
Hand off in `careeros jobs list --status queued --order urgent` order.

## Step 2: resume

Follow `.claude/skills/tailor-resume/SKILL.md` with `JOB`. Store RESULT as `steps.resume`.
If it reports `qa_hard_fails` non-empty after its own fix loop, continue (qa-review will judge).

## Step 3: cover letter (per tier rule)

`rule = tier_cfg.cover_letter` (`always` | `if_required`).
- `always`: follow `.claude/skills/write-cover-letter/SKILL.md`.
- `if_required`: only if `posting.description_text` says a cover letter is required/requested, in either
  word order (regex `(required|must|please|include|attach|submit|upload)\b.{0,40}cover letter|cover letter.{0,40}\b(required|must|please)`),
  and no opt-out wording (opt-out regex `\b(no|not|don't|do not|without)\b[^.;]{0,30}cover letter|cover letter[^.;]{0,30}\b(optional|not required|not needed|not necessary)`),
  both case-insensitive -> follow the skill; else skip and record
  `steps.cover_letter = {"skipped": "not_required"}`.
Store RESULT as `steps.cover_letter`.

## Step 4: QA with one regeneration cycle

`regenerations = 0`. Loop:
1. Follow `.claude/skills/qa-review/SKILL.md` with `JOB`. Store RESULT as `steps.qa`.
2. If `pass`: break.
3. If `next_action == "regenerate"` and `regenerations < max_regenerations`:
   - `regenerations += 1`; update `JOB/qa.json` field `regenerations`.
   - For each distinct `skill` in `regenerate[]` (order: tailor-resume, then write-cover-letter):
     follow that SKILL.md again with `JOB --suggestions "<its suggestions joined by '; '>"`.
   - Continue the loop (qa-review runs again).
4. Else (fail after the allowed regeneration, or `next_action == "action_item"`): break with
   `action_items.append("qa_failed_twice: " + top 2 fail_reasons)`.

## Step 5: status

```
if steps.qa.pass:
    status = "needs_review" if tier == "A" or tier_cfg.review_required non-empty else "queued"
    n = category's categories.yaml new_category_reviews_remaining (0 if unset)
    done = number of OTHER job dirs under data/jobs/ whose score.json category == this category and
           that have a prepare.json (a rerun of this job never counts; config is never edited)
    if done < n: status = "needs_review"; action_items.append("new_category_review: <category> (<n - done> left)")
else:
    status = "needs_review"
```
Tier A always ends `needs_review` with `action_items.append("tier_a_review: review resume + cover letter before submitting <company> <title>")` (priority H).
If `steps.cover_letter.facts_shortfall` is true: `action_items.append("cover_letter_facts: add 2 company facts for <company>")`.
Metric questions (`.claude/skills/_shared/resume_writing_rules.md`, OVERRIDE): for each entry of `JOB/resume.json`
`meta.metric_questions`, add a separate item `metric_question: <bullet_id>: <question>` (type `question`, priority
L, needs `phone`, no `--job`: it is about the profile, not this job) unless an open Action Item already starts
with `metric_question: <bullet_id>:`. They never change `status`.
Any RESULT that contained `ACTION_ITEM` is appended verbatim.

Outreach: if `tier_cfg.outreach == "always"`, note `"outreach": "run /find-contacts then /draft-outreach"` in
the final RESULT (do not run them here; they run after apply).

## Step 6: render the cover letter for pasting

If QA passed and `JOB/cover_letter.md` exists, run
`.venv/bin/python templates/cover_letter/render.py JOB/cover_letter.md`
It writes `JOB/cover_letter.txt` (the body apply-job pastes into forms) and `JOB/cover_letter.pdf`
(a missing LaTeX engine is a warning: the .txt is still written). A nonzero exit means the letter is
not usable: status `needs_review`, `action_items.append("cover_letter_render: <stderr first line>")`.
`resume.pdf` comes from tailor-resume's render step.

## Step 7: record

Write `JOB/prepare.json`:
```json
{"job_id": "...", "prepared_at": "<ISO>", "status": "queued|needs_review|skipped", "tier": "B",
 "category": "...", "fit": 78, "regenerations": 0, "qa_pass": true, "qa_mean": 8.2,
 "steps": {"score": {...}, "resume": {...}, "cover_letter": {...}, "qa": {...}},
 "action_items": ["..."], "files": ["score.json", "resume.json", "resume.txt", "resume.tex", "resume.pdf", "cover_letter.md", "cover_letter.txt", "cover_letter.pdf", "qa.json"]}
```
Append to `JOB/log.md`: `- YYYY-MM-DD HH:MM:SS [prepare-job] status=<s> tier=<t> fit=<n> qa_pass=<b> regenerations=<n> action_items=<n>`
(format `- YYYY-MM-DD HH:MM:SS [<skill>] <message>`, local time, identical to `store.append_log`; e.g. `date '+%F %T'`).

Then record the final status in both `JOB/status.json` and the tracker row:
`.venv/bin/careeros job status <job_id> <queued|needs_review|skipped> --note "<reason, e.g. qa pass tier A | skip_reason>"`.
(If the tracker is locked the op is queued; `careeros tracker flush` later.)

Before adding action items, run `.venv/bin/careeros action list` once and skip any item for which an
open row with the same JobID and Type already exists (a rerun must not duplicate items). Then for
each remaining action item run
`.venv/bin/careeros action add "<text>" --type <review|qa_fail|profile_gap|other> --job <job_id> --priority <H|M> --needs <laptop|phone|anytime> --dedupe`
(`--dedupe` makes the CLI enforce the same rule: if an open item with the same job + type exists it
prints the existing id and adds nothing; `profile_gap` for profile-gap items; `laptop` for anything
that needs the repo or a browser, e.g. tier_a_review; `phone` for quick answers; default `anytime`).
When `gate.urgent` is true and `gate.action_note` is non-empty, append it to the text (`... — <action_note>`)
so the item shows the posting's close date.
If the CLI is unavailable the caller applies them from RESULT.

## Finish: RESULT (last line)

`RESULT: {"skill":"prepare-job","job_id":"...","status":"queued","tier":"B","category":"swe_backend","fit":78,"decision":"prepare","skip_reason":null,"qa_pass":true,"qa_mean":8.2,"regenerations":0,"cover_letter":true,"files":["..."],"ACTION_ITEMS":["..."],"outreach":null,"urgent":false,"closes_at":null}`
