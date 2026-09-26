# career-os

Job-search automation for one person. It finds postings on public job boards, scores them against your
preferences, tailors a one-page résumé and cover letter from a single master profile, QA-checks every
word against that profile, applies through Chrome where it's safe, and tracks everything in a spreadsheet.
The repo ships code plus a fictional candidate ("Alex Example"); your own data never enters it.
All AI work runs through your Claude Code subscription. There is no API key.

## Get started

**→ [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)**: clone, install, fill in your profile, and run
`careeros doctor` until it has no FAIL. About 20 minutes to your first tailored application.

```sh
git clone https://github.com/m0hamedb3ngab5ia/career-os-template.git career-os && cd career-os
python3 -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/careeros init      # copies the example candidate into profile/ and config/ (gitignored)
.venv/bin/careeros doctor    # FAILs until you replace the example data with your own
```

## How it works

- **Scout** (`careeros scout --sync`): pulls the job boards listed in `config/companies.yaml` (Greenhouse,
  Lever and Ashby adapters built in), runs the prefilters you turn on, and stores each posting in
  `data/jobs/<id>/`. Everything is set in `config/targets.yaml: scout`: which sources to fetch, and which
  filters apply (title keywords, seniority, blocked countries, blocklist, flagged companies, ghost jobs),
  each with its own keywords or thresholds.
- **Safety** (`careeros safety check`): every posting gets a verdict (pass, review or block) with reason codes
  and evidence. Levels per code are yours to change in `config/targets.yaml: safety.levels`.
- **Score** (`/score-job`): category, fit 0-100 and tier (A dream list, B strong fit, C volume) from `config/`.
- **Tailor** (`/tailor-resume`, `/write-cover-letter`): builds a résumé and letter only from bullets in
  `profile/master.yaml`, cited by id, with numbers frozen.
- **QA** (`python -m careeros.qa`, `/qa-review`): fabrication audit, banned phrases, confidential terms,
  the example-identity guard and a critic score; one regeneration, then an Action Item.
- **Apply** (`/apply-job`): fills the form in Chrome with your standard answers only. Tier B/C on
  Greenhouse/Lever/Ashby submit after QA; Tier A and every other ATS stop before submit for you.
- **Track** (`data/JobTracker.xlsx`, `/inbox-sync`): statuses, Action Items for anything uncertain, and
  Gmail replies moved into the tracker.

`/prepare-job` runs score, tailor, cover letter and QA for one job. `prepare-job` and `apply-job` both run
`careeros doctor --quiet` first and stop while the example data is still in place.

## What you configure vs what's reusable

Every file in `examples/` opens with "What this file is / What you must fill in / What you can leave as is".
Personal lines carry `# INSERT: <what, format, example>`; generic ones say `reusable default: fine to keep`.

**You configure (personal):**
- `profile/master.yaml`: identity, education, experience and project bullets (each with an `id`), skills, narratives
- `profile/standard_answers.yaml`: work authorization, school, links, phone, address, the `eeo:` block
- `profile/confidential_terms.yaml`: your employer's internal names (QA hard-fails on them)
- `profile/voice/samples/`: 2-5 letters or emails you wrote, then `/learn-voice`
- `config/targets.yaml`: `candidate` (level, graduation, salary floors, work authorization), `location`, `industries`
- `config/companies.yaml`: `dream_list`, `already_applied`, `blocklist` (your current employer), `searches.keywords`
- `config/categories.yaml`: `bullet_priority` = entry ids from your `master.yaml`

**Reusable as shipped:**
- `config/categories.yaml`: the categories, title and skill keywords
- `config/companies.yaml`: the starter `boards` list, prestige tiers and scoring
- `config/targets.yaml`: seniority filter, thresholds, tiers, tier rules, volume caps, safety lists
- `config/qa.yaml`: every QA rule and the banned-phrases list
- `config/pipeline.yaml`: paths, schedule, `llm.runner: claude_code`
- `templates/`, `.claude/skills/`, `src/careeros/`: the code, the same for everyone

## Reference

### Commands

```sh
.venv/bin/careeros init [--link DIR]          # create profile/ + config/ (copy examples, or symlink your private repo)
.venv/bin/careeros doctor [--quiet]           # setup checklist; exit 1 on any FAIL
.venv/bin/careeros scout --sync               # pull boards, prefilter, store, sync the tracker
.venv/bin/careeros jobs list [--status queued]
.venv/bin/careeros job show <id>              # also: job status <id> <status> [--note]
.venv/bin/careeros action list                # also: action add "<what>" --type <t> --needs laptop|phone|anytime
.venv/bin/careeros tracker sync               # also: tracker init | flush | applied-count | upsert
.venv/bin/careeros stats
.venv/bin/careeros prune [--yes] [--json]     # retention: dry run lists old files; --yes removes them
.venv/bin/python -m careeros.qa data/jobs/<id>   # deterministic QA
```

Until `init` has run, every command except `init` and `doctor` stops with "run `careeros init`".

### Skills

| Skill | Does |
|---|---|
| `/score-job` | category, fit score, tier, hard-filter fails for one posting |
| `/tailor-resume` | resume.json from master bullets by id, then render .tex/.pdf/.txt |
| `/write-cover-letter` | 120 to 250 words following `templates/cover_letter/skeleton.md` |
| `/answer-question` | one free-text application answer from profile facts, or `needs_review` |
| `/qa-review` | truth trace, keyword coverage, ATS safety, banned phrases, confidential terms, critic rubric |
| `/prepare-job` | runs the four above in order for one job (after `careeros doctor --quiet`) |
| `/apply-job` | Chrome applier per `src/careeros/apply/adapters.md` (after `careeros doctor --quiet`) |
| `/inbox-sync` | Gmail to tracker status updates, push on interview |
| `/find-contacts` | recruiter or engineer at the company: name, LinkedIn URL, email guess |
| `/draft-outreach` | LinkedIn note, message, cold email drafts from `templates/outreach/` |
| `/learn-voice` | extracts writing patterns from `profile/voice/samples/` into the style guide |

### Daily loop

1. `careeros scout --sync` pulls new postings into `data/jobs/`.
2. `/prepare-job data/jobs/<id>` for each job worth it. Output lands in the job dir; failures become Action Items.
3. Apply session (Chrome open, Claude in Chrome extension on): `/apply-job data/jobs/<id>` per job.
4. `/inbox-sync` reads Gmail and moves statuses (screening, interview, rejected), pushes on interviews.
5. Work the Action Items tab in the tracker (`careeros action list`).

### Autonomy tiers (`config/targets.yaml`)

| Tier | Who | Submit | Cover letter | Outreach |
|---|---|---|---|---|
| A | dream list | never automatic; full prep, you submit | always | always |
| B | fit >= 85 | auto on Greenhouse/Lever/Ashby after QA | always | if a contact is found |
| C | fit >= 70 | auto on Greenhouse/Lever/Ashby after QA | only if required | never |

Workday, iCIMS, Taleo and other ATSs are assisted only: the applier fills what it can and stops at
the review page. Per-job override via the tracker `Override` column.

### Action item types

`Action Items` tab of the tracker (type, what, link, priority, needs), mirrored in each job's `log.md`.
Types: `captcha`, `bot_detection`, `review`, `question`, `salary`, `qa_fail`, `send_linkedin`,
`send_email`, `profile_gap`, `laptop_required`, `scam_suspected`, `other`. Screenshots referenced by an
item live in `data/jobs/<id>/screenshots/`.

### Safety rules

- Never fabricate. Every bullet, claim and number traces to `profile/master.yaml` by id.
- Never apply as the example candidate: `careeros doctor` fails on it, and QA's `example_identity` check
  hard-fails any résumé or letter carrying its name or email.
- Never auto-send on LinkedIn. Drafts only; you send.
- Never guess legal, salary, sponsorship or demographic answers. Only `profile/standard_answers.yaml`
  values are used; anything else is an Action Item.
- Never leak the current employer's internal names: `profile/confidential_terms.yaml` is a hard QA gate.
- Never click submit twice. Never solve CAPTCHAs; bot detection is logged in
  `src/careeros/apply/detection.yaml` and the company goes to manual apply.
- Never apply to the blocklist (`config/companies.yaml`), the current employer, or blocked industries.
- At most two applications per company per 90 days (`volume.max_per_company_per_90_days`).

### Keeping your data private

`profile/`, `config/`, `CLAUDE.local.md`, `data/` and `.reviews/` are gitignored. Keep them in your own
**private** repo and link them in with `careeros init --link ~/career-private` (steps in
[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md#9-keep-your-data-private-recommended)). `--link` refuses to
replace a real (non-symlink) `profile/` or `config/`; move those into the private repo first.
`CLAUDE.local.md` is where personal context for Claude goes; Claude Code loads it automatically.

### Keeping data/ small

`careeros prune` applies `config/pipeline.yaml: retention` (weekly via `schedule.prune`). It is a dry run
unless you pass `--yes`.
- Closed jobs (rejected, withdrawn, ghosted) lose their apply step screenshots 30 days after closing; the
  confirmation screenshot stays.
- Postings never prepared (found, scored, skipped) are trimmed to a stub after 90 days: ids, company, title,
  URLs and dates stay (dedupe and repost checks need them), the description is cut to a short preview.
- Never touched: active jobs, `submitted/` copies, `seen.json`, `posting_history.json`, the scam registries.
  Set a value to 0 to turn that rule off.

### Folder map

```
examples/      the fictional candidate: config/ + profile/ (copied by `careeros init`)
config/        targets.yaml, categories.yaml, companies.yaml, qa.yaml, pipeline.yaml   [gitignored]
profile/       master.yaml (only source of truth), standard_answers.yaml, confidential_terms.yaml, voice/   [gitignored]
templates/     resume/ (LaTeX + render.py), cover_letter/ (skeleton + render.py), outreach/, followup_email/
src/careeros/  scout/ (Greenhouse/Lever/Ashby APIs), apply/ (ATS adapters, questions, session), doctor.py,
               tracker.py, qa.py, store.py, retention.py, cli.py, bootstrap.py
.claude/skills Claude Code skills (table above)
data/          jobs/<id>/ (posting.json, score.json, resume.*, cover_letter.*, answers.json, qa.json, log.md ...), JobTracker.xlsx   [gitignored]
docs/          GETTING_STARTED.md, CODE_REVIEW_PROMPT.md
tests/         pytest (uses examples/ and temp dirs only)
```

The tracker lives at `data/JobTracker.xlsx` by default (tabs: Jobs, Action Items, Contacts, Log, Config).
Point `config/pipeline.yaml: paths.tracker_xlsx` elsewhere to keep it in another folder.

### LLM cost

Everything runs through the Claude Code subscription: skills invoked interactively (`/score-job ...`)
or headless (`claude -p "/score-job data/jobs/<id>" --output-format json`). No Anthropic API key exists
in this repo and `config/pipeline.yaml: llm.runner` is `claude_code`.

### Contributing / review

All changes land by PR, tests first (`CLAUDE.md`). `/review <PR>` in Claude Code runs Claude and Codex
reviews in parallel and merges their findings (`docs/CODE_REVIEW_PROMPT.md`). From Codex directly:
`$review <PR>`. Headless Codex only: `scripts/review.sh <PR>`.
Tests: `.venv/bin/python -m pytest -q` (`-m unit`, `-m integration`); they need no personal files.

## License

[PolyForm Noncommercial 1.0.0](LICENSE.md): free for personal and other noncommercial use. Commercial use
needs a separate license from the copyright holder. Contributions are accepted under the terms in
[CONTRIBUTING.md](CONTRIBUTING.md).
