# The process, start to finish

One path from "I just cloned this" to "I applied and followed up". It is chat-first (DEC-024): you talk to
Claude Code in the repo; the web UI only shows Today and Jobs. Chat equivalents of every old click are in
[CHAT.md](CHAT.md); install and setup are in [GETTING_STARTED.md](GETTING_STARTED.md). Config knobs are written
`file: key` and live in `config/` (defaults in `examples/config/`).

You never need to remember commands. Each stage is "you say X, Claude does Y"; the `careeros ...` commands are
what Claude runs, shown for reference. Each stage lists what you say, what runs as plain code (no AI tokens), the
knobs, and what needs your yes.

## 1. Onboarding (once)

**You say:** "set me up" (Claude runs `careeros init`), "here is my master résumé" (Claude runs `careeros resume add
<file>` and the `extract-master` skill, which proposes a `profile/master.yaml` diff), "what's missing?" (`careeros doctor`).

**Plain code:** init copies `examples/` to `profile/` and `config/`; doctor checks files, example data left,
broken YAML, unknown bullet ids, tools. Readiness must-items block applying until done.

**You must provide:**
- Master résumé (file), then approve the `master.yaml` diff: `profile/master.yaml` is the only source of facts.
- Look approval: Claude shows you the rendered master résumé; say "looks good" (or what to change) and Claude
  runs `careeros resume approve-look` (readiness item `resume_look_approved`). A new master résumé resets it.
  No job prep before this.
- `profile/standard_answers.yaml`: work authorization, sponsorship, EEO, pronouns, address, links, and
  how-did-you-hear (with `prefer:` keywords that pick the dropdown option).
- `config/targets.yaml`: `categories` (roles), `location`, salary floors, `industries`.
- `config/companies.yaml`: `blocklist` (include your employer) and `dream_list` (Tier A, you submit these).
- `config/categories.yaml: bullet_priority` per category; `profile/confidential_terms.yaml`.
- Optional: 2-5 writing samples in `profile/voice/samples/`, then `/learn-voice`.

Done when `careeros doctor` shows no FAIL.

## 2. Applying (repeat)

**You say:** "find jobs", "score and prepare the best ones", "fill the form for job X", "submit it". **Claude does:**
`careeros scout --sync` finds jobs, then the prefilter (code) drops obvious misses. `/score-job` first runs the
hard filters in code (`careeros job filters`): a dealbreaker (too many required years, a senior title, a blocked
company or country, salary under the minimum) ends scoring as skip with fit 0. Otherwise it gives category, fit and tier. `/prepare-job <id>` tailors the résumé, writes the letter, runs QA. `careeros apply plan
<id>` builds `fill_plan.json`; `careeros apply fill <id>` stages the form in the browser and never submits.
You confirm, then submit.

**Plain code:** scout, prefilter (`targets.yaml: scout.filters`, seniority, blocked countries, ghost jobs), safety
and scam gate, caps, ranking, retries, the fill plan. AI runs only in score, prepare, QA and essay answers.

**Knobs:**
- How many: `pipeline.yaml: runs.preset` (small, medium, large, max, custom) and `runs.presets.*`;
  `targets.yaml: volume.max_applications_per_day`, `max_per_company_per_90_days`; `runs.prepare.stop_at_daily_cap`.
- Which: `targets.yaml: categories.primary|secondary|excluded`, `thresholds.min_fit_to_prepare`,
  `thresholds.tier_a_min_fit`, `tier_rules`, `industries`.
- Review or fill-only: `targets.yaml: tiers.<A|B|C>.review_required` (parts you must look at first);
  `categories.yaml: new_category_reviews_remaining` (first outputs of a new category always get reviewed).
- Auto-submit (off by default, opt in): `targets.yaml: tiers.B.auto_submit`, `tiers.C.auto_submit`,
  `safety.auto_submit_ats`, `safety.pause_auto_submit` (true stops every auto-submit), and
  `pipeline.yaml: runs.auto_submit.enabled|allow|manual` for runs.

**Needs your yes:** each Tier A job, any job with `review_required` parts, any QA failure, every Action Item
(unknown question, captcha, legal or salary question), and the final submit unless you opted in above.
Tier A never auto-submits. Submit is clicked at most once per job.

## 3. History and status

You say "what's the status?" or "what needs me?"; Claude runs the matching command:

- `/today`: what needs you, in flight, top queued jobs, last run (read-only, 25 lines).
- `careeros jobs list --status <found|scored|queued|needs_review|applied|...>`; `careeros job show <id>`.
- The tracker `data/JobTracker.xlsx` (Jobs and Action Items tabs); edit only through the CLI.
- `/inbox-sync` reads company mail and moves jobs to confirmed, rejected, interview or offer.
- "Show me my status": Claude runs `careeros view`, local pages as tabs: Setup checklist (until setup is done, then Documents: résumés, saved answers, writing samples), Jobs (what needs you, jobs by stage), Applications.

## 4. After applying

- `/find-contacts <id>` then `/draft-outreach <id>`: drafts only; you send, nothing touches LinkedIn.
- Follow-ups: the drafts include 7-day and 14-day notes; `/today` and Action Items surface what is due.
- `/interview-prep <id>`: STAR outlines from your bullet ids, honest about gaps.
- Rejections and answered questions feed `learn` (standard answers, apply lessons) and scoring tuning
  (a scoring eval set is planned).
- `careeros prune` (dry run unless `--yes`) trims old screenshots and unprepared postings per
  `pipeline.yaml: retention`.

## Changing your mind in chat

You say it; Claude edits files or runs existing commands (no special commands exist for these):
- "Don't apply to <company>": Claude adds it to `config/companies.yaml: blocklist.companies` (YAML edited, comments
  kept) and sets that company's open jobs (found, scored, queued, needs_review) to skipped with
  `careeros job status <id> skipped --note blocklist`. Scout and score-job keep enforcing the blocklist.
- "Unblock <company>": the reverse, removing it from the blocklist.
- "This posting is fine" / "mark safe": `careeros safety clear`, then `careeros job status <id> queued`.
- "Close these action items": `careeros action done <id>` for each id.

## Pick up in any chat

All state is files: `data/` (jobs, runs), `profile/`, `config/` and the tracker. Nothing lives only in a chat.
Open any Claude chat in the repo and say "where are we?"; Claude runs `/today` and tells you what needs you and
what is in flight.
For unattended runs and scheduling see GETTING_STARTED.md step 12 and `docs/COMMANDS.md`.
