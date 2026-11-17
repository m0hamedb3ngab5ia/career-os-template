# Feature catalogue

Everything career-os can do, grouped by what you are trying to do, in job-search order.
You never have to remember commands: say what you want in Claude Code chat and Claude runs them.
Full flags: [COMMANDS.md](COMMANDS.md). Chat equivalents of old UI clicks: [CHAT.md](CHAT.md).
The step-by-step path: [PROCESS.md](PROCESS.md).

## Start here

1. Follow [GETTING_STARTED.md](GETTING_STARTED.md): clone, install, `careeros init`, fill in your profile.
2. Run `careeros doctor` until it shows no FAIL.
3. Open a chat and say `/today`: it shows what needs you and the one next step.
4. Say "what can you do?" any time; Claude points here.

**High-odds strategy:** fresh postings first, then a short sourced note to a real person (referrals first) right after applying. Cold applications convert far worse than referred ones. Details and sources: [PROCESS.md](PROCESS.md) ("How career-os gets you interviews").

Hard rules: no invented résumé facts, no guessed legal or salary answers, never automates LinkedIn, never sends a message for you, never submits Tier A.

## 1. Set up

| Feature | What it does | How to use | REQ |
|---|---|---|---|
| Init | Copies the example candidate into `profile/` and `config/` (gitignored). | `careeros init`; or "set me up" | |
| Doctor | Checks setup: example data left, broken YAML, unknown bullet ids, missing tools. | `careeros doctor`; or "what's missing?" | REQ-102 |
| Readiness checklist | Blocks applying until the must-items are done. | Setup card on Today; `careeros doctor` | REQ-102, REQ-103, REQ-131 |
| Master résumé store | Stores your résumés; the first one is the master. | `careeros resume add <file>`, `careeros resume list` | REQ-100 |
| Extract master | Proposes a `profile/master.yaml` update from the master résumé; you approve the diff. | `/extract-master`; `careeros resume propose-master <file>`, `careeros resume keep-master` | REQ-099 |
| Look approval | You confirm how the rendered master résumé looks; prep is blocked until then. | Say "looks good"; `careeros resume approve-look` | REQ-143 |
| Writing samples | Learns your writing style from samples you add. | Put files in `profile/voice/samples/`, then `/learn-voice` | REQ-101 |
| Saved answers | Stores standard answers (work authorization, EEO, address, links) once. | `careeros learn answer "<question>" "<answer>"`, `careeros learn list` | REQ-107 |
| Credentials | Stores job-site logins outside git for the apply skill. | `careeros creds set <site>` | |
| Catalogue view | This list in the app: search box, commands with a copy button. | "What can I do?" button on Today, or open `/catalogue` in `careeros ui` | REQ-165 |
| Setup view | Static HTML tabs: Setup, Documents, Jobs, Search, Applications. | `careeros view --open` | |
| Template sync | Compares and pulls this copy against the public template. | `careeros sync status`, `careeros sync pull` | |

## 2. Find jobs

| Feature | What it does | How to use | REQ |
|---|---|---|---|
| Scout | Pulls job boards, prefilters, stores new postings, syncs the tracker. | `careeros scout --sync`; or "find new jobs" | |
| Company boards | Finds the Greenhouse/Ashby/Lever board for a company name. | `careeros company find-board <name>` | |
| Add one job | Adds a posting by URL, or from alert-email JSON. | `careeros job add <url>`; `careeros job describe <id> --text-file <path>` | |
| Check any job | Score a pasted posting without scouting it. | Paste it in chat, run `/score-job` | REQ-114 |
| Job list and detail | Lists jobs by status; shows one job's documents, score, safety. | `careeros jobs list [--status queued]`, `careeros job show <id>`; UI Jobs | REQ-128, REQ-129 |
| Search filters | Shows every filter, its value, and how many postings each removed. | Say "only remote jobs posted in the last 14 days"; Search tab of `careeros view` | |
| Block a company | Skips a company everywhere (scout and score keep enforcing it). | Say "don't apply to X"; "unblock X" reverses | |
| Safety checks | Flags scam or ghost postings; one Action Item per dream company. | `careeros safety ghost-items`; say "this posting is fine" to clear | |

## 3. Decide what to apply to

| Feature | What it does | How to use | REQ |
|---|---|---|---|
| Score job | Scores fit 0-100, tier A/B/C, hard-filter fails, prepare or skip, and gaps. | `/score-job <id>`; `careeros run score` for a batch | |
| Hard filters | Dealbreaker rules checked in code before any AI call. | `careeros job filters <id>` | |
| Top picks | Best queued jobs by fit, with reasons. | UI Today; `/today` | REQ-127, REQ-130 |
| Pick jobs | Tick the jobs the pipeline may touch; new postings start unticked. | Tick in UI Jobs; `careeros job select <id>` | REQ-104 |
| Recredit skips | Re-checks low-fit skips against what your profile evidences. | `careeros jobs recredit [--write]` | |
| Skip insights | Explains skip reasons, near-miss skills, filter unlock counts. | `careeros advise`; `careeros advise apply <id>` | REQ-152 |
| Watch list | Raises an Urgent item and email for new fitting jobs at watched companies. | `watch: true` in `config/companies.yaml`; sent by `careeros tick` | REQ-159 |
| Outside advice | Judges a pasted article or post against this repo's principles. | `/advice` | |

## 4. Prepare résumé and cover letter

| Feature | What it does | How to use | REQ |
|---|---|---|---|
| Prepare job | Runs score, tailor, cover letter, QA for one job. | `/prepare-job <id>` | |
| Match and reuse | Scores each stored résumé against a job; reuses one if it is good enough. | `careeros resume match <id>`, `careeros resume pick <id>` | REQ-111, REQ-112, REQ-115 |
| Bullet shortlist | Picks the best profile bullets for a posting without AI. | `careeros resume shortlist <id>` | |
| Tailor résumé | Builds a one-page résumé from profile bullets by id only. | `/tailor-resume <id>` | |
| Cover letter | Writes a short letter in your voice with sourced company facts. | `/write-cover-letter <id>` | |
| QA review | Critic gate: deterministic checks plus a fabrication audit. | `/qa-review <id>`; `python -m careeros.qa data/jobs/<id>` | |
| Review résumé | AI suggestions and comments on a stored résumé; you accept each. | `/review-resume <rid>` | REQ-094 |
| Edit résumé | Answers one annotation with a new suggestion or reply. | `/edit-resume <rid> <aid>`; `careeros resume annotations <rid>` | REQ-095, REQ-096 |
| Résumé rules | Saves a general résumé rule for later runs. | `careeros resume rule-add "<heading>" "<rule>"` | |
| Answer a question | Answers one form question from saved answers, or drafts an essay. | `/answer-question` | |

## 5. Apply

| Feature | What it does | How to use | REQ |
|---|---|---|---|
| Fill plan | Builds the question plan for a Greenhouse or Ashby form. | `careeros apply plan <id>` | |
| Fast fill | Stages the form in a browser via Playwright; never submits. | `careeros apply fill <id>` | |
| Apply in Chrome | Stages or submits one prepared application in Chrome. | `/apply-job <id>`; `careeros run apply --job <id>` | |
| Batches | Plans and runs many jobs to a chosen stop point. | `careeros batch create <ids> --stop-at prepare`, `careeros batch run <id>` | REQ-117, REQ-118 |
| Budgeted runs | Score or prepare in budgeted batches; pause, cap, catch up. | `careeros run prepare --preset small`, `careeros run list`, `careeros run pause` | |
| Locks | Stops two runs touching one job. | `careeros job lock\|unlock\|check <id>` | |
| Status changes | Records applied, skipped, and so on, with channel and note. | `careeros job status <id> <status> --channel referral` | |
| Action Items | Things only you can do (open questions, legal answers). | "what needs me?"; `careeros action list`, `careeros action add`, `careeros action done <id>` | REQ-123 |

## 6. Outreach and referrals

| Feature | What it does | How to use | REQ |
|---|---|---|---|
| Outreach targets | Lists high-yield jobs worth a note, one per company. | `careeros outreach targets --top 3`; "draft outreach for my top 3" | REQ-161 |
| Find contacts | Finds likely recruiter, hiring manager, team lead; builds search links. | `/find-contacts <id>` | |
| Contact emails | Fills `contacts.json` with email guesses (optional Apollo and Hunter keys). | `careeros outreach emails <id>` | |
| Draft outreach | Drafts connection note, message, email, follow-ups; never sends. | `/draft-outreach <id>` | |
| Outreach QA | Gates drafts (length, sourced fact, ask); gives a Gmail compose link. | `careeros outreach qa <id>` | REQ-162 |
| Record a send | Marks what you sent by hand and starts the follow-up clock. | `careeros outreach sent <id>` | REQ-154 |
| Network match | Imports your LinkedIn export and shows jobs where you know someone. | `careeros network import <csv>`, `careeros network match` | |

## 7. Follow-ups and reminders

| Feature | What it does | How to use | REQ |
|---|---|---|---|
| Follow-up nudges | Raises an Action Item for applied jobs and sent outreach with no reply. | `careeros tick` | REQ-154 |
| Reach-out nag | Asks you to reach out for applied jobs after 14 days. | `careeros tick` | REQ-156 |
| Inbox sync | Reads company mail, updates statuses, adds Action Items. | `/inbox-sync`; "check my inbox" | |
| Scheduler | Runs `tick` on a schedule (macOS LaunchAgent). | `careeros schedule install`, `uninstall`, `status` | |
| Tick | One pass: follow-ups, urgent items, digest. | `careeros tick [--dry-run]` | |

## 8. Notifications

| Feature | What it does | How to use | REQ |
|---|---|---|---|
| Email digest | Daily or weekly summary emailed to yourself. | `careeros notify setup`, `careeros notify test`, `careeros notify digest` | REQ-155 |
| Urgent emails | One email for a fresh, high-fit job at a watched company. | `notify.urgent` in `config/pipeline.yaml` | REQ-159 |
| Hiring seasons | Raises the weekly volume target in busy windows. | `volume.season_multiplier` in `config/targets.yaml` | REQ-160 |
| Today in chat | The dashboard in at most 25 lines, read-only. | `/today` | |

## 9. Interview prep

| Feature | What it does | How to use | REQ |
|---|---|---|---|
| Interview prep | Maps posting requirements to STAR outlines from your bullets; says where evidence is missing. | `/interview-prep <id>` | |

## 10. Learn from results

| Feature | What it does | How to use | REQ |
|---|---|---|---|
| Yield report | Interview rate per channel (cold, referral, sourced) with confidence interval. | `careeros yield report` | |
| Stats | Counts of jobs by status. | `careeros stats` | |
| Learn lessons | Records answers and form hurdles per site for next time. | `careeros learn lesson "<text>" --ats greenhouse` | |
| Voice learning | Measures your style from samples into the style guide. | `/learn-voice` | |

## 11. Settings and config

| Feature | What it does | How to use | REQ |
|---|---|---|---|
| Targets and companies | Roles, locations, salary floors, dream list, blocklist. | "change `<key>` in `config/targets.yaml` to `<value>`" | |
| Pipeline config | Runs, outreach, follow-ups, notifications, budgets. | Same, in `config/pipeline.yaml` | |
| Web dashboard | Read-only Today and Jobs on 127.0.0.1. | `careeros ui` | REQ-128 |
| Tracker spreadsheet | Excel workbook of all jobs; written only by the CLI. | `careeros tracker sync`, `flush`, `applied-count` | |

## 12. Maintenance

| Feature | What it does | How to use | REQ |
|---|---|---|---|
| Prune | Deletes old job data per retention settings. | `careeros prune` (dry run), `--yes` | |
| Storage | Shows disk use and snapshots. | `careeros storage` | |
| Verify the UI | Drives the real app on a fictional candidate to prove a change works. | `/verify-careeros` | |
| Tests | Runs the whole pipeline on the fake candidate. | `.venv/bin/python -m pytest -q` | |
