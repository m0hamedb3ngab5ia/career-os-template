# career-os

Job-search automation for one candidate. Finds postings, scores them, tailors a résumé and cover
letter from one master profile, QA-checks everything, applies through Chrome where allowed, tracks
the pipeline in a spreadsheet, and syncs status from Gmail. Design in `ARCHITECTURE.md`.

Anyone can use it: the repo ships the code plus a fictional example candidate ("Alex Example") in
`examples/`. Your own profile and config never enter this repo.

## Quick start for a new user

```sh
git clone <this repo> career-os && cd career-os      # keep it outside iCloud/Dropbox-synced folders
python3 -m venv .venv && .venv/bin/pip install -e ".[test]"
brew install tectonic                                  # LaTeX engine; without it you get .tex only, no PDF
.venv/bin/careeros init                                # copies examples/{profile,config} -> profile/, config/
```

`careeros init` never overwrites an existing `profile/` or `config/`, and prints the files to edit.
Replace Alex Example with yourself (every personal line is marked `# EDIT`):

- `profile/master.yaml`: identity, education, experience bullets (each with an `id`), skills, narratives
- `profile/standard_answers.yaml`: work authorization, school, links, phone, address, the `eeo:` block
- `profile/confidential_terms.yaml`: your employer's internal codenames and id patterns (QA hard-fails on them)
- `profile/voice/samples/`: 2 to 5 letters or emails you wrote, then run `/learn-voice`
- `config/targets.yaml`: `candidate` (level, graduation, `min_base_usd`, `salary_dropdown_floor_usd`), `location`
- `config/companies.yaml`: `dream_list`, `already_applied`, `blocklist` (your current employer), `boards`
- `config/categories.yaml`: `bullet_priority` = entry ids from your `master.yaml`

Then:

```sh
.venv/bin/careeros scout --sync     # pull every board in config/companies.yaml, create data/JobTracker.xlsx
.venv/bin/careeros jobs list --status found
```

Until `init` has run, every command stops with "run `careeros init`".

## Keeping your data private

`profile/`, `config/`, `CLAUDE.local.md`, `data/` and `.reviews/` are gitignored. The safest setup is to
keep them in your own **private** git repo and link them in:

```sh
mkdir -p ~/career-private && cp -R examples/profile examples/config ~/career-private/
# edit them there, `git init` + push to a private remote, optionally add ~/career-private/CLAUDE.local.md
.venv/bin/careeros init --link ~/career-private
```

`--link` creates `profile`, `config` (and `CLAUDE.local.md` when the directory has one) as symlinks into
that directory. It refuses to replace a real (non-symlink) `profile/` or `config/`; move those into the
private repo first. `CLAUDE.local.md` is where personal context for Claude goes (who you are, where your
notes live); Claude Code loads it automatically and it is never committed.

## Folder map

```
examples/      the fictional candidate: config/ + profile/ (copied or used as a template by `careeros init`)
config/        targets.yaml (what/how autonomously), categories.yaml, companies.yaml, qa.yaml, pipeline.yaml   [gitignored]
profile/       master.yaml (only source of truth), standard_answers.yaml, confidential_terms.yaml, voice/     [gitignored]
templates/     resume/ (LaTeX + render.py), cover_letter/ (skeleton + render.py), outreach/, followup_email/
src/careeros/  scout/ (Greenhouse/Lever/Ashby APIs), apply/ (ATS adapters, questions, session), tracker.py, qa.py, store.py, cli.py, bootstrap.py
.claude/skills Claude Code skills (see list below)
data/          jobs/<id>/ (posting.json, score.json, resume.*, cover_letter.*, answers.json, qa.json, log.md ...), JobTracker.xlsx   [gitignored]
tests/         pytest (uses examples/ only)
```

The tracker lives at `data/JobTracker.xlsx` by default (tabs: Jobs, Action Items, Contacts, Log, Config).
Point `config/pipeline.yaml: paths.tracker_xlsx` elsewhere if you want it in another folder.

## Daily loop

1. `careeros scout --sync` pulls new postings from every board in `config/companies.yaml` into `data/jobs/`.
2. `/prepare-job data/jobs/<id>` for each queued job: score, tailor résumé, write cover letter, answer
   known questions, QA. Output lands in the job dir; failures become Action Items.
3. Apply session (Chrome open, Claude in Chrome extension on): `/apply-job data/jobs/<id>` per job.
   Tier B/C on Greenhouse/Lever/Ashby submit automatically after QA; everything else stops at the
   filled form with a screenshot and an Action Item.
4. `/inbox-sync` reads Gmail, moves statuses (screening, interview, rejected), pushes on interviews.
5. Work the `Action Items` tab in the tracker (`careeros action list`).

## Autonomy tiers (`config/targets.yaml`)

| Tier | Who | Submit | Cover letter | Outreach |
|---|---|---|---|---|
| A | dream list | never automatic; full prep, you submit | always | always |
| B | fit >= 85 | auto on Greenhouse/Lever/Ashby after QA | always | if a contact is found |
| C | fit >= 70 | auto | only if required | never |

Workday, iCIMS, Taleo and other ATSs are assisted only: the applier fills what it can and stops at
the review page. Per-job override via the tracker `Override` column.

## Where Action Items appear

`Action Items` tab of the tracker (type, what, link, priority, needs), mirrored in each job's
`log.md`. Types: `captcha`, `bot_detection`, `review`, `question`, `salary`, `qa_fail`,
`send_linkedin`, `send_email`, `profile_gap`, `scam_suspected`, `other`. Screenshots referenced by an item live in
`data/jobs/<id>/screenshots/`.

## LLM cost

Everything runs through the Claude Code subscription: skills invoked interactively (`/score-job ...`)
or headless from the pipeline (`claude -p "/score-job data/jobs/<id>" --output-format json`).
No Anthropic API key exists in this repo and `config/pipeline.yaml: llm.runner` is `claude_code`.
API billing would only come into play if you later want unattended server runs or an Agent SDK
build; that is not enabled and needs an explicit opt-in.

## Skills

| Skill | Does |
|---|---|
| `/score-job` | category, fit score, tier, hard-filter fails for one posting |
| `/tailor-resume` | resume.json from master bullets by id, then render .tex/.pdf/.txt |
| `/write-cover-letter` | 120 to 250 words following `templates/cover_letter/skeleton.md` |
| `/answer-question` | one free-text application answer from profile facts, or `needs_review` |
| `/qa-review` | truth trace, keyword coverage, ATS safety, banned phrases, confidential terms, critic rubric |
| `/prepare-job` | runs the four above in order for one job |
| `/apply-job` | Chrome applier per `src/careeros/apply/adapters.md` |
| `/inbox-sync` | Gmail to tracker status updates, push on interview |
| `/find-contacts` | recruiter or engineer at the company: name, LinkedIn URL, email guess |
| `/draft-outreach` | LinkedIn note, message, cold email drafts from `templates/outreach/` |
| `/learn-voice` | extracts writing patterns from `profile/voice/samples/` into the style guide |

## Safety rules

- Never fabricate. Every bullet, claim and number traces to `profile/master.yaml` by id.
- Never auto-send on LinkedIn. Drafts only; the candidate sends.
- Never guess legal, salary, sponsorship or demographic answers. Only `profile/standard_answers.yaml`
  values are used; anything else is an Action Item.
- Never leak the current employer's internal names: `profile/confidential_terms.yaml` is a hard QA gate.
- Never click submit twice. Never solve CAPTCHAs; bot detection is logged in
  `src/careeros/apply/detection.yaml` and the company goes to manual apply.
- Never apply to the blocklist (`config/companies.yaml`), the current employer, or blocked industries.
- One application per company per role family; two per company per 90 days.

## Contributing / review

All changes land by PR. `/review <PR>` in Claude Code runs Claude and Codex reviews in parallel
against the PR's base branch and merges their findings (`docs/CODE_REVIEW_PROMPT.md`).
From Codex directly: `$review <PR>`. Headless Codex only: `scripts/review.sh <PR>`.
Tests: `.venv/bin/python -m pytest -q` (`-m unit`, `-m integration`); they need no personal files.
