# Getting started

From a fresh clone to your first application. The easy way: open the repo in Claude Code and say
**"set me up"**. Claude follows the [`onboard`](../.claude/skills/onboard/SKILL.md) skill, runs every command for
you, and picks up where you left off if you stop. This page is the same checklist, for reading or doing by hand.
Every command runs from the repo root. Nothing is ever submitted for you unless you turn on auto-submit later.

## 1. Check what you need

| Need | Why | How to check / install |
|---|---|---|
| macOS or Linux | the tool assumes a normal shell | |
| Python 3.11+ | runs the `careeros` tool | `python3 --version`; macOS: `brew install python@3.12` |
| Claude Code | does all the AI work (scoring, writing, QA) on your subscription; no API key | https://docs.claude.com/en/docs/claude-code, then run `claude` once to sign in |
| tectonic (or `pdflatex`) | turns résumés into PDFs | `brew install tectonic` |
| Chrome | only for applying and the Handshake source | |

## 2. Clone and install

Use a plain folder, not iCloud Drive or Dropbox (synced folders break the Python environment).

```sh
git clone https://github.com/m0hamedb3ngab5ia/career-os-template.git career-os && cd career-os
python3 -m venv .venv && .venv/bin/pip install -e ".[test]"
```

Works when `.venv/bin/careeros --help` prints a list of commands.

## 3. Create your private files

```sh
.venv/bin/careeros init
.venv/bin/careeros doctor
```

`init` copies a made-up candidate, "Alex Example", into `profile/` and `config/`. Both folders are gitignored: your
data never goes into git. `doctor` is the checklist. Right now it shows about 11 FAIL lines. That is expected: each
one says "this is still Alex's data". Steps 4 to 7 clear them all.

| FAIL says | Fixed in |
|---|---|
| `profile/master.yaml: identity.* is still the example value` | step 4 |
| `experience / projects / education / leadership id '...' is from the example` | step 4 |
| `profile/standard_answers.yaml: identical to the example file` | step 6 |
| `bullet_priority` id does not exist (appears after step 4) | step 7 |

## 4. Your profile, from your résumé

`profile/master.yaml` holds every fact your résumés and letters may use. Nothing else is ever invented.

```sh
.venv/bin/careeros resume add ~/path/to/your-resume.pdf --type master
```

Then in Claude Code run `/extract-master` ([skill](../.claude/skills/extract-master/SKILL.md)). It proposes a full
`master.yaml` from your résumé and shows the diff. Check it, add any missing numbers, then approve it:

```sh
.venv/bin/python -c "import careeros.master_sync as m; print(m.approve('.'))"
```

(`m.reject('.')` throws the proposal away.) By hand instead: edit `profile/master.yaml` directly. Replace
the `identity` block, and replace Alex's entries (`acme`, `initech_intern`, `widgetizer`, `state_u`, `acm`) with
your own, each with a new `id` and 2-4 true bullets.

## 5. Confidential terms

If your employer has internal project names or codes, list them in `profile/confidential_terms.yaml: terms`. QA
blocks any document that contains one. No such terms: `terms: []` and `patterns: []`.

## 6. Standard answers

`profile/standard_answers.yaml` holds the answers application forms reuse word for word: work authorization,
sponsorship, school, links, phone, start date, and the `eeo:` block ("Decline to self-identify" is always fine).
Replace each line marked `# INSERT`, then delete the comment. Claude asks you these one group at a time during
onboarding and never guesses a legal answer.

## 7. Targets and companies

| File | Set |
|---|---|
| `config/targets.yaml` | `candidate` (level, graduation, salary floors, work authorization), `location`, roles in `scout.filters` |
| `config/companies.yaml` | `dream_list` (you review these yourself; never auto-submitted), `blocklist.companies` (your current employer) |
| `config/categories.yaml` | each `bullet_priority` list: your own experience ids, most relevant first |
| `config/pipeline.yaml` | fine as is; `paths.tracker_xlsx` moves the tracker spreadsheet |

Run `.venv/bin/careeros doctor` again until it exits with no FAIL. WARN lines are advice. An `# INSERT` WARN on a
line where Alex's value is also your true answer (say `"Yes"`) goes away when you delete the comment.

## 8. Approve how your résumé looks

```sh
.venv/bin/careeros resume approve-look
```

It prints where your master résumé PDF is. Open it; run the command once you are happy with it. Preparing jobs
waits for this (`careeros resume look-check` exits 0 when done).

## 9. Choose your job sources

Turn on any mix. Company boards are the usual start.

| Source | What it finds | What it needs | How to turn on |
|---|---|---|---|
| Company boards (Greenhouse, Ashby, Lever) | every open job at the companies you list | company names | edit `boards:` in `config/companies.yaml`; add by name with `careeros company find-board "Name"` |
| Handshake | your school's Handshake job search, read-only | a Handshake account; `pip install -e ".[fast-apply]"`, `playwright install chromium`; you sign in once in the apply browser | say "turn on Handshake" (the [onboard](../.claude/skills/onboard/SKILL.md) skill, step 9b), then uncomment the `Handshake` line under `boards:` |
| LinkedIn job-alert emails | companies hiring for your LinkedIn alerts, added as company boards | LinkedIn alerts by email, a Gmail label, the Claude desktop browser pane or a Gmail connector | say "job alerts" ([job-alerts](../.claude/skills/job-alerts/SKILL.md) skill) |

`careeros company find-board` prints ready-to-paste `boards:` lines. Check a common company name's board really is
that company before adding it. LinkedIn itself is never automated: the job-alerts route only reads emails LinkedIn
already sent you, and you sign in to Gmail yourself.

## 10. First jobs

```sh
.venv/bin/careeros scout --sync                 # pull the boards; nothing is sent anywhere
.venv/bin/careeros run score --preset small     # Claude scores up to 10 jobs
.venv/bin/careeros jobs list --status scored
.venv/bin/careeros run prepare --job <id>       # résumé, cover letter and QA for one job; never applies
.venv/bin/careeros job show <id>
```

Scout found nothing? `data/scout_last.json` shows which filter removed what; loosen that filter in
`config/targets.yaml: scout.filters`. A job ends as `needs_review` when something needs your answer:
`careeros action list`, then `careeros action done <id> --answer "..."`.

A prepared job folder `data/jobs/<id>/` holds `score.json` (fit and why), `resume.pdf`, `cover_letter.md` and
`qa.json` (pass or the reasons). Read the résumé and letter before applying.

## 11. Apply

Greenhouse and Ashby, fast fill (needs the `[fast-apply]` extra and `playwright install chromium`):

```sh
.venv/bin/careeros apply plan <id>    # every answer it will type, in data/jobs/<id>/fill_plan.json
.venv/bin/careeros apply fill <id>    # fills the form in a separate browser window; never submits
```

Check the form, fill anything it reports as empty, click submit yourself, then
`.venv/bin/careeros job status <id> applied`. Other sites: `/apply-job` ([skill](../.claude/skills/apply-job/SKILL.md))
fills through the Claude in Chrome extension and stops before submit.

## Daily use

- Start each Claude Code chat with `/today`: what needs you, the best new jobs, the last run.
- Then: `scout --sync`, `run score`, `run prepare --job <id>`, review, apply (steps 10-11).
- `/inbox-sync` moves recruiter replies into the tracker. `/job-alerts` weekly refreshes companies from LinkedIn alerts.
- You can say all of this in plain words; [CHAT.md](CHAT.md) lists the commands behind each request.
- Optional: put 2-5 letters you wrote in `profile/voice/samples/` and run `/learn-voice` so letters sound like you.
- Optional dashboard: `pip install -e ".[ui]"`, then `careeros ui` opens Today and Jobs at http://127.0.0.1:8765.
- Optional, macOS: `careeros schedule install` runs scout, score and prepare overnight (see "Unattended runs").
- The full process (follow-ups, statuses, outreach) is in [PROCESS.md](PROCESS.md).

## Keep your data private (recommended)

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

## ATS logins and what the system learns

Applying itself is described in [PROCESS.md](PROCESS.md) (stage 2). Chrome with the Claude in Chrome extension signed in is
needed only for the `/apply-job` path.

If an ATS needs a login, store it once (outside the repo, mode 0600, never committed):

```
careeros creds set workday --username you@example.com      # prompts for the password (hidden)
careeros creds list                                         # sites and usernames, no secrets
```

The file is `~/.careeros/credentials.yaml` (`paths.credentials` in `config/pipeline.yaml`); set
`credentials.backend: keychain` there to keep passwords in the macOS keychain instead. `careeros doctor` warns if the
file is inside a git repo or readable by others. `/apply-job` reads it with `careeros creds get` and never writes a
password into job data or logs.

Every application teaches the next one. A form question nothing in `profile/standard_answers.yaml` answers
becomes an Action Item with the question in its text; answer it once with
`careeros action done <id> --answer "<your answer>"` (or the Answer button in the app) and the answer is added to
`profile/standard_answers.yaml`, so no later application asks it again (`careeros learn answer` adds one by hand;
`--company X` keeps it to one company). Hurdles the applier had to work around on an ATS or at a company are
written to `profile/apply_lessons.yaml` (`careeros learn lesson`, `careeros learn list`) and read before the
next session there.

## Unattended runs (optional, macOS)

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
.venv/bin/careeros run prepare --job <id>         # one job only; run apply --job <id> once it is queued
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
inbox sync never start inside quiet hours (09:00 to 18:00, Recommended); scout and prune ignore them
(`schedule.scout_quiet_hours: true` makes scout wait too). A slot held
back by quiet hours (or a busy runner) runs as soon as it may; it is not lost. It is a **LaunchAgent, not a daemon**: it runs as you, with your Claude
Code login, only while you are logged in to your Mac. Nothing runs while the Mac sleeps, is off or you are logged out.

**Pause, resume, catch up:**

```sh
.venv/bin/careeros run pause --until +2h --reason "interview prep"   # or an ISO time; no --until = until resume
.venv/bin/careeros run resume
.venv/bin/careeros run reset-failures <job_id> --kind apply   # a job out of retries (runs.retry) runs again
.venv/bin/careeros run catch-up --dry-run   # slots missed while the Mac slept or was off
.venv/bin/careeros run catch-up             # run them now (once each)
.venv/bin/careeros run catch-up --dismiss   # or drop them
```

Pausing stops the current run before its next job, and ticks skip what falls due (it is not stored up). Missed
slots never run on their own: they collapse into one pending catch-up that you start or dismiss
(`schedule.missed_runs: skip` drops them instead). With `runs.on_usage_limit: pause` a run that hits your Claude usage
limit also pauses all runs until `careeros run resume` (the Recommended `stop` just waits for the next slot).

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

Step 10 keeps only your data private. Some people instead keep a whole **private copy** of this repo: the same
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
The guard checks the tip tree and every commit the push sends. To know what the template already has, it asks
the template itself (`git ls-remote <push URL>`), never local remote-tracking refs; if the template can't be
reached, or a `url.*.insteadOf` rule would send that query to a different URL, it scans the whole pushed history
instead (slower, never less safe).

## FAQ

**What does it cost?** Nothing beyond your Claude Code subscription. All LLM work runs through Claude
Code (`claude`), there is no API key in this repo, and the job-board APIs are public. Heavy use counts
toward your subscription's usage limits.

**Does it touch LinkedIn?** No automation, ever. It writes LinkedIn notes and messages as drafts for you
to send, and builds LinkedIn search URLs. The LinkedIn discovery source is off by default and never uses
Easy Apply.

**What gets submitted automatically?** Nothing by default: `tiers.B.auto_submit` and `tiers.C.auto_submit`
in `config/targets.yaml` ship as `false`. If you opt in (`true`), only Tier B and C jobs (not on your dream list)
on Greenhouse, Lever or Ashby are submitted, after QA passed. Tier A (dream list) is never submitted for you. Workday, iCIMS, Taleo and other systems stop at the filled review page with
an Action Item. Salary, legal or unknown questions are never guessed; they become Action Items.

**How do I stop it?** Press Esc (or Ctrl-C) in Claude Code to interrupt a running skill. To make
everything stop before submit, keep `auto_submit: false` under `tiers.B` and `tiers.C` (the default), or set
`safety.pause_auto_submit: true`, in `config/targets.yaml`. For one job, set its `Override` column in the tracker to `A`. Nothing runs in the
background unless you install the scheduler (`careeros schedule install`); `careeros run pause` stops scheduled
and running batches, `careeros schedule uninstall` removes it. Batches never submit anything.

**Can I try it without my own data?** Yes: `.venv/bin/python -m pytest -q` runs the whole pipeline on the
fake candidate. The skills refuse to apply with that data (`careeros doctor` fails on it).
