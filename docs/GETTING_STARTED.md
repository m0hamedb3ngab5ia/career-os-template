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

Scout pulls every board in `config/companies.yaml`, drops senior / wrong-location / blocklisted titles,
stores each posting in `data/jobs/<id>/` and creates the tracker `data/JobTracker.xlsx`. Nothing is
sent anywhere.

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

## Updating from upstream

```sh
git pull
.venv/bin/pip install -e ".[test]"
.venv/bin/careeros doctor
```

Your data is gitignored (or lives in your private repo), so a pull never conflicts with it. New settings
show up in `examples/`; compare with your copy (`diff examples/config/targets.yaml config/targets.yaml`)
and let `careeros doctor` tell you if a required key is missing.

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
background unless you schedule it yourself.

**Can I try it without my own data?** Yes: `.venv/bin/python -m pytest -q` runs the whole pipeline on the
fake candidate. The skills refuse to apply with that data (`careeros doctor` fails on it).
