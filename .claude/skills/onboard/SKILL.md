---
name: onboard
description: Walk a new user from a fresh clone to their first application, one checklist step at a time, resuming where they left off. Use when someone says "set me up", "onboard me", "how do I start", or pastes this repo's link into a new chat.
---

# onboard

You are setting up career-os for someone who knows little about it. Go one step at a time. For each step: say in
one or two plain sentences what it does, run the command yourself (the user only answers questions and does the
steps marked **user**), show what success looks like, and fix the common failure before moving on. The human-readable
mirror of this checklist is `docs/GETTING_STARTED.md`; keep them in step.

Hard rules (from `CLAUDE.md`): never invent résumé facts, never guess legal/EEO/salary answers (ask, or leave an
Action Item), never automate LinkedIn, never submit anything for the user during onboarding, never type a password.

## Where are we? (run this first, every time)

Resume from the first step that is not done:

| Check | Done when | Go to |
|---|---|---|
| `python3 --version` | 3.11 or newer | step 1 |
| `ls .venv/bin/careeros` | exists | step 2 |
| `ls profile config` | both exist | step 3 |
| `.venv/bin/careeros doctor` | no FAIL lines (exit 0) | steps 4-7, by the FAIL text |
| `.venv/bin/careeros resume look-check` | exit 0 | step 8 |
| `config/companies.yaml: boards` | holds boards the user chose | step 9 |
| `.venv/bin/careeros jobs list` | lists jobs | step 10 |

Say which step you are resuming at and why ("doctor still fails on `standard_answers.yaml`, so step 6").

## 1. Prerequisites

Check each and say what is missing; nothing else is needed yet.

| Need | Check | If missing |
|---|---|---|
| Python 3.11+ | `python3 --version` | macOS: `brew install python@3.12` |
| Claude Code | you are running in it; `claude --version` for headless runs | https://docs.claude.com/en/docs/claude-code |
| A LaTeX engine (résumé PDFs) | `tectonic --version` | `brew install tectonic` |
| Chrome (applying, Handshake) | installed | only needed from step 11; optional until then |

The checkout must not be inside iCloud Drive or Dropbox (synced folders break `.venv`). If `pwd` shows
`Mobile Documents` or `Dropbox`, ask the user to clone elsewhere first.

## 2. Install

```sh
python3 -m venv .venv && .venv/bin/pip install -e ".[test]"
```

Success: `.venv/bin/careeros --help` prints the command list. Failure `requires a different Python`: step 1.
Failure `No module named careeros` on macOS in a synced folder: `chflags -R nohidden .venv`, or move the clone.

## 3. Create profile/ and config/

```sh
.venv/bin/careeros init
```

It copies the fictional candidate "Alex Example" into `profile/` and `config/` (gitignored, never committed).
Then run `.venv/bin/careeros doctor`. Tell the user: about 11 FAIL lines are expected; they all mean "still Alex's
data" and steps 4-7 clear them.

## 4. The profile from their résumé (`profile/master.yaml`)

This is the only source of résumé facts, so it must be true and complete.

1. **user**: give you the path to their current résumé (PDF or DOCX).
2. `.venv/bin/careeros resume add <file> --type master`
3. Run the `/extract-master` skill. It writes a proposed master.yaml next to the real one and prints a diff.
4. Walk the user through the diff section by section (identity, education, experience, projects, skills). Ask for
   any missing number rather than inventing one.
5. On their yes: `.venv/bin/python -c "import careeros.master_sync as m; print(m.approve('.'))"`
   (the same action as the dashboard's approve button; `m.reject('.')` drops the proposal).

Check: no `example_data ... profile/master.yaml` FAIL left in `careeros doctor`. If ids `acme`, `initech_intern`,
`widgetizer`, `state_u` or `acm` still show, the proposal kept Alex's entries: delete them from the proposal and
approve again. Doctor may now FAIL on `bullet_priority`: fix in step 7.

## 5. Confidential terms (`profile/confidential_terms.yaml`)

Ask: "Does your current employer use internal project names or codes that must never appear in an application?"
Put them in `terms:`; if none, set `terms: []` and `patterns: []`.

## 6. Standard answers (`profile/standard_answers.yaml`)

Application forms reuse these word for word. Ask the user each `# INSERT` question in small groups (work
authorization and sponsorship, school and degree, links and phone, start date, then the `eeo:` block, where
"Decline to self-identify" is always fine). Never fill a legal or EEO answer yourself. Write each answer and delete
its `# INSERT` comment.

Check: doctor no longer shows `standard_answers.yaml: identical to the example file`.

## 7. Targets and pipeline (`config/`)

Ask, then edit, keeping comments:

- `config/targets.yaml`: `candidate` (level, graduation, salary floors, work authorization), `location`
  (preferred cities, work modes), roles they want (the `scout.filters` title keywords), industries to boost or block.
- `config/companies.yaml`: `dream_list` (companies they want to review by hand: Tier A, never auto-submitted) and
  `blocklist.companies` (their current employer at least).
- `config/categories.yaml`: every `bullet_priority` list uses their own experience ids, most relevant first.
- `config/pipeline.yaml`: usually fine as is. Mention `paths.tracker_xlsx` if they want the tracker elsewhere.

Run `.venv/bin/careeros doctor` until it exits 0. WARN lines are advice, not blockers: an `# INSERT` line whose
example value is also their true answer just needs its comment deleted.

## 8. Approve the résumé look

`.venv/bin/careeros resume approve-look` prints where the master résumé PDF is. Ask the user to open it and say
yes before you run it (that is what it records). Check: `.venv/bin/careeros resume look-check` exits 0.

## 9. Choose job sources

Present all three, one line each, and ask which to turn on (any mix; (a) is the usual start):

| Source | Finds | Needs | Cost |
|---|---|---|---|
| (a) Company boards | every open job at companies you list (Greenhouse, Ashby, Lever) | company names | nothing; public APIs |
| (b) Handshake | your school's Handshake job search | a Handshake account, Playwright, sign-in once in the apply browser | one sign-in; reads only |
| (c) LinkedIn job-alert emails | companies hiring for the roles in your LinkedIn alerts, turned into (a) boards | LinkedIn alerts by email, Gmail, the Claude desktop browser pane (or a Gmail connector) | a few minutes per refresh |

**(a) Company boards.** The example `boards:` list is a starting set; ask whether to keep, trim or replace it. To
add companies by name:

```sh
.venv/bin/careeros company find-board "Company One" "Company Two"   # or --file names.txt, one per line
```

It prints `boards:` lines; paste the found ones into `config/companies.yaml`. A miss means the company uses
another ATS (Workday, custom): leave it out. Common names can hit a different company with the same slug: open the
printed board URL and check the jobs look right before adding.

**(b) Handshake.** Read-only: scout runs Handshake's own job search inside a browser the user signed in to; no
password or cookie is stored, and it never applies, saves or messages.

1. `.venv/bin/pip install -e ".[fast-apply]" && .venv/bin/playwright install chromium`
2. Open the apply browser (a separate Chrome profile in `~/.careeros/chrome-apply`, on 127.0.0.1:9223):
   `.venv/bin/python -c "from pathlib import Path; from playwright.sync_api import sync_playwright; from careeros.apply import browser as b; p = sync_playwright().start(); b.ensure(b.DEFAULT_CDP, Path('~/.careeros/chrome-apply').expanduser(), p.chromium.executable_path); p.stop()"`
3. **user**: in that window, go to https://app.joinhandshake.com and sign in. Leave the window open.
4. Uncomment the `Handshake` line under `boards:` in `config/companies.yaml` and set its `queries` to their roles.

Failure `not signed in: sign in to Handshake in the apply browser`: step 3 again. Failure `is the apply browser
running?`: step 2 again (it closes when the Mac restarts).

**(c) LinkedIn job-alert emails.** Run the `/job-alerts` skill; it ends by adding boards for (a).

## 10. First scout, score and prepare

```sh
.venv/bin/careeros scout --sync                 # pulls the boards; nothing is sent anywhere
.venv/bin/careeros jobs list --status found
.venv/bin/careeros run score --preset small     # scores up to 10 jobs with Claude (uses your subscription)
.venv/bin/careeros jobs list --status scored
```

Scout keeps 0 jobs: the filters in `config/targets.yaml: scout.filters` are too tight for these boards; open
`data/scout_last.json` to see which filter removed what, and loosen that one. Pick one well-scored job with the
user, then:

```sh
.venv/bin/careeros run prepare --job <id>       # résumé, cover letter, QA; never applies
.venv/bin/careeros job show <id>
```

Review together: `resume.pdf`, `cover_letter.md`, `qa.json`. `needs_review` means an Action Item
(`.venv/bin/careeros action list`) needs the user's answer: `careeros action done <id> --answer "..."`.

## 11. Apply (fast fill; the user submits)

Greenhouse and Ashby forms:

```sh
.venv/bin/careeros apply plan <id>     # writes data/jobs/<id>/fill_plan.json; show the user every answer
.venv/bin/careeros apply fill <id>     # fills the form in the apply browser (127.0.0.1:9223); never submits
```

`apply fill` needs the `[fast-apply]` extra and `playwright install chromium` (step 9b, part 1). It reports any
required field it left empty: name each one to the user. **user**: check the form, fill what is empty, click submit
themselves. Then `.venv/bin/careeros job status <id> applied`. Other ATSs: `/apply-job` (Claude in Chrome
extension), which stops before submit by default.

## 12. Daily loop

Tell the user what a normal day looks like, then stop:

- Start each chat with `/today`: what needs them, top jobs, last run.
- `scout --sync`, `run score`, `run prepare --job <id>`, review, apply (steps 10-11).
- Replies: `/inbox-sync`. Refresh LinkedIn-alert companies weekly with `/job-alerts`.
- Optional, macOS: `careeros schedule install` runs scout, score and prepare overnight (never applies).
- Optional: 2-5 letters they wrote in `profile/voice/samples/`, then `/learn-voice`, so letters sound like them.
- Keeping their data in a private repo: `docs/GETTING_STARTED.md`, "Keep your data private".
