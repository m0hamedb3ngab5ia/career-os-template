# Getting started

From a fresh clone to your first tailored application in about 20 minutes. Every command is meant to be
copy-pasted from the repo root. Nothing is submitted anywhere until step 10, and only when you run it.

## Prerequisites

| Need | Why | Install |
|---|---|---|
| macOS or Linux | the CLI and skills assume a POSIX shell | |
| Python 3.12+ | the `careeros` package | `python3 --version`; on macOS `brew install python@3.12` |
| Claude Code subscription + CLI | every skill (scoring, tailoring, QA, applying) runs through it; no API key | install from https://docs.claude.com/en/docs/claude-code, then run `claude` once to log in |
| Claude in Chrome extension | only for applying (`/apply-job` drives your browser) | Chrome Web Store: "Claude in Chrome", then sign in |
| Homebrew + tectonic | turns résumés and cover letters into PDFs | `brew install tectonic` (or any `pdflatex`) |
| gh + codex (optional) | only for `/review` of code changes | `brew install gh`, `npm install -g @openai/codex` |

## 1. Clone (outside iCloud / Dropbox)

Synced folders hide files inside `.venv` and create "file 2.py" duplicates. Use a plain folder:

```sh
mkdir -p ~/dev && cd ~/dev
git clone https://github.com/m0hamedb3ngab5ia/career-os-template.git career-os
cd career-os
```

## 2. Python environment

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest -q -m unit        # optional: should be all green, uses only the fake example data
```

## 3. Create your profile/ and config/

```sh
.venv/bin/careeros init
```

This copies the fictional candidate "Alex Example" from `examples/` into `profile/` and `config/`
(both gitignored). It never overwrites existing files. Run the checklist once to see what's left:

```sh
.venv/bin/careeros doctor
```

Expect a list of FAIL lines: the profile still holds the example identity, experience ids and answers.
The skills refuse to prepare or submit anything until those are gone.

## 4. Fill in these first (minimum viable set)

Every personal line in these files carries an `# INSERT: <what goes here, format, example>` comment.
Replace the value; delete the comment once the line holds your real value. Lines labeled
`reusable default: fine to keep` can stay as they are.

| # | File | What to fill in | Time |
|---|---|---|---|
| 1 | `profile/master.yaml` → `identity` | name, email, phone, location, LinkedIn, GitHub | 2 min |
| 2 | `profile/master.yaml` → `experience`, `projects`, `education` | 2-3 real entries, each with a new `id` (e.g. `northwind`) and 2-4 bullets (`northwind.1`, ...). One fact per bullet, real numbers only. Delete the example entries | 8 min |
| 3 | `profile/master.yaml` → `skills`, `narratives` | tools you can defend; 1-2 true sentences about what drives you | 2 min |
| 4 | `profile/standard_answers.yaml` | every `answer` with an INSERT comment (work authorization, sponsorship, school, links, phone, address) and the `eeo:` block ("Decline" is fine) | 3 min |
| 5 | `config/targets.yaml` → `candidate`, `location`, `industries` | level, graduation, salary floors, work authorization, preferred cities | 2 min |
| 6 | `config/companies.yaml` → `dream_list`, `blocklist` | companies you want to review yourself (Tier A); your current employer in `blocklist.companies` | 1 min |
| 7 | `config/categories.yaml` → `bullet_priority` | replace `acme, initech_intern, widgetizer` with your own entry ids, most relevant first | 1 min |
| 8 | `profile/confidential_terms.yaml` | your employer's internal codenames (or `terms: []`, `patterns: []`) | 1 min |

Later, when you have time: put 2-5 letters or emails you wrote in `profile/voice/samples/` and run
`/learn-voice` in Claude Code, so cover letters sound like you.

## 5. Run the doctor until there is no FAIL

```sh
.venv/bin/careeros doctor
```

- **FAIL** blocks everything (example data left, broken YAML, a `bullet_priority` id that doesn't exist,
  `claude` not installed). Fix and rerun. Exit code 0 means ready.
- **WARN** is advice: an `# INSERT` line still identical to the example (if the example value is also your
  true answer, e.g. `"Yes"`, delete its `# INSERT` comment), no LaTeX engine, no voice samples, no gh/codex.

## 6. First scout

```sh
.venv/bin/careeros scout --sync
.venv/bin/careeros jobs list --status found
```

Scout pulls every board in `config/companies.yaml`, applies the prefilters enabled in
`config/targets.yaml: scout.filters` (by default: title keywords, seniority, blocked countries, blocklist,
flagged companies and ghost jobs), stores each posting in `data/jobs/<id>/` and creates the tracker
`data/JobTracker.xlsx`. Nothing is sent anywhere.

To change what scout keeps:

| Want | Set in `config/targets.yaml` |
|---|---|
| only some job-board sources | `scout.sources: [greenhouse]` |
| keep senior roles | `scout.filters.seniority: false` (or edit `seniority.exclude_title_keywords`) |
| keep every title, no category filter | `scout.filters.title: false` |
| never skip old postings | `scout.filters.ghost: false`, or tune `safety.ghost` thresholds |
| treat a safety check differently | `safety.levels: {SCAM_FREE_EMAIL_RECRUITER: block, GHOST_OLD_POST: off}` |

## 7. Prepare one job

Pick an id from the list, start Claude Code in the repo, and run the skill:

```sh
claude
```

```
/prepare-job data/jobs/<id>
```

It checks `careeros doctor` first, then scores the posting, tailors a one-page résumé from your bullets,
writes a cover letter when the tier calls for one, and runs QA (one regeneration if needed). The last
line is a `RESULT` with `queued`, `needs_review` or `skipped`.

## 8. Review the output

```sh
ls data/jobs/<id>/
.venv/bin/careeros job show <id>
```

| File | What to check |
|---|---|
| `score.json` | category, fit 0-100, tier, why it would be skipped |
| `resume.pdf` / `resume.txt` | every bullet is yours, word for word or lightly rephrased; numbers unchanged |
| `cover_letter.md` | 120-250 words, two concrete facts about the company, sounds like you |
| `qa.json` | `pass`, and `fail_reasons` if not |
| `log.md`, `prepare.json` | what each step did |

To get the letter as `.txt` / `.pdf` (needed by `/apply-job`):

```sh
.venv/bin/python templates/cover_letter/render.py data/jobs/<id>/cover_letter.md
```

Open items (questions it couldn't answer, reviews) are in the tracker's Action Items tab:

```sh
.venv/bin/careeros action list
```

## 9. Keep your data private (recommended)

`profile/`, `config/`, `CLAUDE.local.md` and `data/` are gitignored, so they never go into this repo. To
back them up and use them from several machines, keep them in your own **private** repo and link them in:

```sh
mkdir -p ~/career-private
mv profile config ~/career-private/
cd ~/career-private && git init && git add . && git commit -m "my career-os data" && cd -
# push ~/career-private to a PRIVATE remote (e.g. `gh repo create career-private --private --source ~/career-private --push`)
.venv/bin/careeros init --link ~/career-private
```

`--link` makes `profile`, `config` (and `CLAUDE.local.md` if that folder has one) symlinks into
`~/career-private`. `CLAUDE.local.md` is where personal notes for Claude go; it is never committed.

## 10. Apply (when you're ready)

Open Chrome with the Claude in Chrome extension signed in, then in Claude Code:

```
/apply-job data/jobs/<id>
```

It checks `careeros doctor`, the QA result, daily and per-company caps, and a scam gate before touching
the form. See the FAQ for what submits on its own.

## 11. Unattended runs (optional, macOS)

Once single jobs look right, the system can score and prepare in batches on a schedule. Python ranks the jobs and
enforces the budgets; each job is one headless Claude Code call (`claude -p`, your subscription). Runs never apply:
jobs end `queued` or `needs_review` and you still run `/apply-job` yourself.

**One-time setup, interactively (an unattended run can't answer a login prompt):**

1. Log in to Claude Code in a terminal: run `claude`, then `/login`. Scheduled runs use this same login.
2. If you will turn on the scheduled inbox sync, authenticate the Gmail MCP once in `claude` with `/mcp` before any
   unattended run. The job already lists it in `config/pipeline.yaml: schedule.jobs.inbox_sync.mcp_servers`
   (`[gmail]`, Recommended); if that login lapses the run stops with `auth_required` instead of hanging. Score and
   prepare need no MCP server, so the global `runs.required_mcp_servers` (MCP servers every run needs) stays `[]`
   (Recommended).
3. Review `config/pipeline.yaml: llm.allowed_tools`, the only tools a headless call may use (the shipped list
   (Recommended) is what score-job and prepare-job need). A tool a skill needs but that is missing ends the run with
   `permission_denied`, never a hang.

**Try it by hand first:**

```sh
.venv/bin/careeros run score --dry-run          # which jobs would go first, and why; calls nothing
.venv/bin/careeros run score --preset small     # 10 jobs or 30 minutes, whichever comes first
.venv/bin/careeros run status                   # what is running, last runs, what goes next and why
.venv/bin/careeros run list                     # past runs and their stop reasons
.venv/bin/careeros run show <run_id> --log      # one run's log; --json for every attempt
.venv/bin/careeros run prepare --preset small   # then prepare the best-scored jobs (never applies)
```

Budget presets (`config/pipeline.yaml: runs.preset`): small, medium (Recommended: 25 score / 5 prepare jobs, 90
minutes), large, max, or custom (`runs.custom`). `--max-jobs N` and `--max-minutes M` override one run. A run ends
with a stop reason: `completed`, `budget_reached`, `time_budget`, `daily_cap` and `paused` are normal;
`usage_limit`, `auth_required`, `permission_denied`, `timeout`, `consecutive_failures` and `doctor_failed` need you
(the detail says what to do). A job that fails twice (Recommended: retry once) becomes an Action Item.

**Schedule it:**

```sh
.venv/bin/careeros schedule install     # LaunchAgent: `careeros tick` every 15 minutes
.venv/bin/careeros schedule status      # installed / loaded, last tick, next run per job, missed runs
.venv/bin/careeros tick --dry-run       # what a tick would do right now
.venv/bin/careeros schedule uninstall   # remove it
```

The tick runs what is due in `config/pipeline.yaml: schedule.jobs`: scout every 3 hours, score nightly at 01:00,
prepare nightly at 02:00, prune weekly (all Recommended). Each job takes `every_hours`, `every_days` or times of day
(`at: ["01:00"]`). A nightly job waits for its time after you install the schedule; it does not run at once.
`inbox_sync` (08:00 and 18:00) is in the file but `enabled: false` until the inbox-sync skill is finished; once you
turn it on it needs the Gmail MCP logged in (step 2 above), or it stops with `auth_required`. Score, prepare and
inbox sync never start inside quiet hours (09:00 to 18:00, Recommended); scout and prune ignore them. A slot held
back by quiet hours (or a busy runner) runs as soon as it may; it is not lost. It is a **LaunchAgent, not a daemon**: it runs as you, with your Claude
Code login, only while you are logged in to your Mac. Nothing runs while the Mac sleeps, is off or you are logged out.

**Pause, resume, catch up:**

```sh
.venv/bin/careeros run pause --until +2h --reason "interview prep"   # or an ISO time; no --until = until resume
.venv/bin/careeros run resume
.venv/bin/careeros run catch-up --dry-run   # slots missed while the Mac slept or was off
.venv/bin/careeros run catch-up             # run them now (once each)
.venv/bin/careeros run catch-up --dismiss   # or drop them
```

Pausing stops the current run before its next job, and ticks skip what falls due (it is not stored up). Missed
slots never run on their own: they collapse into one pending catch-up that you start or dismiss.

**Where the logs are:** `data/runs/<run_id>/` (`run.json`, `run.log`, `attempts/` with each call's raw output),
`data/runs/launchd.out.log` and `data/runs/launchd.err.log` (the scheduler's own output). `careeros prune` removes
run logs after 30 days and whole runs after 365 (Recommended).

## Updating from upstream

```sh
git pull
.venv/bin/pip install -e ".[test]"
.venv/bin/careeros doctor
```

Your data is gitignored (or lives in your private repo), so a pull never conflicts with it. New settings
show up in `examples/`; compare with your copy (`diff examples/config/targets.yaml config/targets.yaml`)
and let `careeros doctor` tell you if a required key is missing.

## Keeping a private copy in sync

Step 9 keeps only your data private. Some people instead keep a whole **private copy** of this repo: the same
code plus a committed `personal/` folder (profile, config, `CLAUDE.local.md`, linked with
`careeros init --link personal`). The rule for such a copy: code, docs and skill changes land in the public
template first, then get merged into the private copy; only personal values are committed privately.

One-time setup in the private copy:

```sh
git remote add template https://github.com/<you>/career-os-template.git   # the public template
.venv/bin/careeros sync install-hook      # pre-push guard: personal paths never go to a template URL
```

List the files your copy keeps different on purpose in a committed `.template-sync-keep` (one glob per line,
with a reason), so they don't show up as drift:

```text
README.md        # my own README
.gitattributes   # LFS rules for my data
```

Day to day:

```sh
.venv/bin/careeros sync status     # exit 0 in sync, 1 template commits not merged yet, 2 drift
.venv/bin/careeros sync pull       # sync/<date> branch from main, merge the template (no fast-forward),
                                   # run pytest (+ ui/ npm ci, test, build), print the push + `gh pr create` commands
```

- **Drift** = files that differ from the template outside personal paths and `.template-sync-keep`. They are
  changes that belong in the template: branch from `template/main`, apply them there, open the PR, then
  `careeros sync pull`.
- `pull` refuses on uncommitted changes. On conflicts it stops (exit 3) with the files to resolve and the
  commands to finish (`git add`, `git commit --no-edit`) or abort (`git merge --abort`). `--no-checks` skips the
  local checks, `--branch` names the branch, `--remote` / `--template-branch` pick another remote or branch.
- The checks run locally, so a private repo does not need its own CI minutes.

Settings (git config in the private copy):

| Key | Default | Meaning |
|---|---|---|
| `careeros.personalPaths` | `personal/ profile/ config/ CLAUDE.local.md data/` (Recommended) | paths that never go to the template and never count as drift (comma or space separated) |
| `careeros.templateUrlPattern` | `*career-os-template*` (Recommended) | remote URLs the pre-push guard protects (shell glob) |

`install-hook` is idempotent and will not replace a pre-push hook it did not write unless you pass `--force`
(the old one is kept as `pre-push.bak`).

## FAQ

**What does it cost?** Nothing beyond your Claude Code subscription. All LLM work runs through Claude
Code (`claude`), there is no API key in this repo, and the job-board APIs are public. Heavy use counts
toward your subscription's usage limits.

**Does it touch LinkedIn?** No automation, ever. It writes LinkedIn notes and messages as drafts for you
to send, and builds LinkedIn search URLs. The LinkedIn discovery source is off by default and never uses
Easy Apply.

**What gets submitted automatically?** Only when you run `/apply-job`, and only Tier B and C jobs
(fit 70+, not on your dream list) on Greenhouse, Lever or Ashby, after QA passed. Tier A (dream list)
is never submitted for you. Workday, iCIMS, Taleo and other systems stop at the filled review page with
an Action Item. Salary, legal or unknown questions are never guessed; they become Action Items.

**How do I stop it?** Press Esc (or Ctrl-C) in Claude Code to interrupt a running skill. To make
everything stop before submit, set `auto_submit: false` under both `tiers.B` and `tiers.C` in
`config/targets.yaml`. For one job, set its `Override` column in the tracker to `A`. Nothing runs in the
background unless you install the scheduler (`careeros schedule install`); `careeros run pause` stops scheduled
and running batches, `careeros schedule uninstall` removes it. Batches never submit anything.

**Can I try it without my own data?** Yes: `.venv/bin/python -m pytest -q` runs the whole pipeline on the
fake candidate. The skills refuse to apply with that data (`careeros doctor` fails on it).
