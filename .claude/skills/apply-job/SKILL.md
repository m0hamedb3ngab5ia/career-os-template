---
name: apply-job
description: Submit (or stage for review) one prepared application through Chrome. Input is a job dir under data/jobs/. Use during an apply session after /prepare-job has produced resume.pdf, cover_letter.txt, answers.json and a passing qa.json.
---

# /apply-job <job_dir>

Drive the ATS form in Chrome for one job, following `src/careeros/apply/adapters.md`. Auto-submit
only when the tier and ATS allow it; otherwise stop before submit and hand off with an Action Item.
Never type anything that is not in the profile, standard answers, answers.json, or cover_letter.txt.

Argument: `data/jobs/<job_id>` (absolute or repo-relative). Everything below refers to files in it.

Shell: one command per Bash call. Runs start this skill headless with `--permission-mode dontAsk` and an allowlist (`.venv/bin/careeros *`, `.venv/bin/python *`, `date *`); a chain (`;`, `&&`, `|`) or an `echo $?` has an unlisted part and the whole call is denied. Read the exit code from the tool result.

## Setup guard (before anything else)

Run `.venv/bin/careeros doctor --quiet` first. If it exits nonzero, STOP before opening a browser:
print its FAIL lines and a `RESULT` with `outcome: failed`, reason `setup: careeros doctor failed`.
Never submit with the example candidate's data (Alex Example) or a half-configured profile.
Every early-stop `RESULT` in this section and in section 1 carries `status`: the job's current status from `status.json`, as is (never `unchanged` or any value not in `applied | needs_review | queued | prepared | skipped`).

Job lock (next): `.venv/bin/careeros job lock <job_id> --owner apply-job --json`. Exit 6 means a run or another
session is working on this job: STOP before opening a browser, change nothing, print a `RESULT` with
`outcome: failed`, reason `locked: <owner from stderr>`. On exit 0 keep `token` and `reentrant` from its JSON;
every `careeros job status` below takes `--lock-token <token>` (and `tracker upsert ... --field Status=` too).
After the final `RESULT`, and on every stop after this point, release it with
`.venv/bin/careeros job unlock <job_id> --token <token>` unless `reentrant` is true (the caller releases it).

## 0. Load tools

`ToolSearch` once: `select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__read_page,mcp__claude-in-chrome__find,mcp__claude-in-chrome__form_input,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__file_upload,mcp__claude-in-chrome__get_page_text,mcp__claude-in-chrome__javascript_tool,mcp__claude-in-chrome__read_network_requests,mcp__claude-in-chrome__tabs_close_mcp`

If the `mcp__claude-in-chrome__*` tools don't load or `tabs_context_mcp` errors (extension off or not connected):
stop with `RESULT` `outcome: failed`, reason `chrome not connected`. No Action Item (the runner reports it as
"Connect Chrome" and the UI offers Retry) and close no tab: a tab already open for this job stays for the retry.

Python runs with `.venv/bin/python` from the repo root.

## 1. Preconditions (all must hold, else stop with the reason)

Read `posting.json`, `score.json`, `status.json`, `qa.json`, `config/targets.yaml`,
`profile/master.yaml`, `profile/standard_answers.yaml`, `src/careeros/apply/detection.yaml`.

| Check | Source | On fail |
|---|---|---|
| no earlier submit: `ApplySession.already_submitted(job_dir)` is False | `apply_session.json` | outcome failed, reason "submit already clicked in an earlier session; check the ATS by hand"; Action Item type `review`; no browser |
| status is `queued` (or `prepared`); `needs_review` only when the effective tier (row below) is A and `prepare.json: qa_pass` is true (then `auto_submit` is forced off: staging for the candidate); a Tier B/C `needs_review` job waits for the human's Approve (status `queued`) | `status.json` | print `RESULT` with `outcome: failed`, reason "status <x>"; no browser |
| `qa.json` top-level `pass` is `true` and `deterministic.pass` is `true` (the qa-review schema) | `qa.json` | outcome failed, reason "qa not passed"; no browser |
| `resume.pdf` exists | job dir | if only `resume.tex`: Action Item type `other` "no PDF; install LaTeX engine (`brew install tectonic`) then rerun /prepare-job"; outcome failed |
| `cover_letter.txt` exists when tier `cover_letter: always`, or posting requires one | job dir, targets.yaml | outcome failed, reason "cover letter missing" |
| detected ATS (adapters.md table, from `posting.apply_url` or `url`) | posting.json | record in session |
| tier from `score.json: tier`; the tracker `Override` column wins if set: read it with `.venv/bin/careeros tracker show <job_id> --json` (`Override` key; `A`/`B`/`C` replace the tier, `manual` or `skip` = no auto-submit) | score.json, tracker | if the command fails: `auto_submit` = false |
| `auto_submit` = tiers[tier].auto_submit AND ats in `safety.auto_submit_ats` AND `safety.json: auto_submit_allowed` (from `careeros safety check`, section 1b: true only when the verdict is pass, "Pause all auto-submit" `safety.pause_auto_submit` is off, and the ATS is allowlisted on its own or the company's domain, reached from the company's board) | targets.yaml, safety.json | if false: proceed in assisted mode (stop before submit) |
| runner verdict: when `CAREEROS_AUTO_SUBMIT` is set (a `careeros run apply` attempt; the runner computed `runs.auto_submit` from `score.json`, `safety.json` and the dream list, reason in `CAREEROS_AUTO_SUBMIT_REASON`) it overrides the `auto_submit` derivation above: `0` = assisted mode, `auto_submit` = false whatever the rows above say (fill and stage the form, never click submit, finish `staged` with status `needs_review`, section 5); `1` = the runner allows it, and the rows above still all have to hold (ATS allowlist, override column, safety, bot detection) for `auto_submit` to be true. Unset = the derivation above | environment | never submit with `CAREEROS_AUTO_SUBMIT=0` |
| company not in `detection.yaml` with `skip_auto: true` | detection.yaml | Action Item `bot_detection` "known bot detection at <company>; apply by hand with prepared materials"; status needs_review; no browser |
| daily cap: `.venv/bin/careeros run cap --check` exits 0 (applications today, by DateApplied, < `volume.max_applications_per_day` x `season_multiplier[month]`; code: `careeros.runs.policy`) | tracker, status history | exit 3: outcome failed, reason "daily cap" |
| company gate: `.venv/bin/careeros company gate <job_id> --json` exits 0. One check for the per-company cap (`volume.max_per_company_per_90_days`, or the company's `company_caps` entry), the rejection cooldown (`volume.same_company_cooldown_days`, lifted for a posting that closes before it ends) and a closed posting | tracker, job dirs, config | exit 3: outcome failed, reason "company <reason>: <detail>"; no browser. `company_cap` / `cooldown`: status unchanged (still queued, retried next session). `closed`, `not_similar`, `already_applied`: permanent, so run `.venv/bin/careeros job status <job_id> skipped --note "company <reason>: <detail>" --lock-token <token>` (a dead job must not keep its slot or retry forever). Keep the JSON as `gate` |

`run cap --check` prints today's count and cap (`--json` for fields); 0 applications when the tracker does not exist yet.

Session order: take jobs in `careeros jobs list --status queued --order urgent` order. Urgent jobs (the
posting closes before a rejection cooldown ends, or two or more similar roles at one company close within
`volume.deadline_cluster_days`) go first so related applications land together, then the earliest close
date, then fit. When `gate.urgent` is true, every Action Item this skill adds for the job ends with
`gate.action_note` (it names the close date). Never open the workbook
directly from this skill; every tracker read/write goes through the `careeros` CLI.

### 1b. Safety gate (before any form fill)

Code: `src/careeros/safety/` (scam, company risk, ghost jobs). Every check yields a reason code, a level
and evidence; the verdict is **pass**, **review** or **block** (`skip` for dead postings).

1. Posting gate, before opening the browser: `.venv/bin/careeros safety check <job_id>`, then read
   `safety.json`:
   - `verdict` block (exit 3) or skip (exit 4): stop. The CLI already opened the Action Item / set the
     status. Print `RESULT` with `outcome: failed`, reason `safety <verdict>: <codes>`.
   - `verdict` review: continue in assisted mode only (`auto_submit` false; stop before submit with a
     `review` Action Item naming the review codes). Never auto-submit a review job.
   - `verdict` pass: `auto_submit_allowed` feeds the preconditions table.
2. Field gate, on every page/step of the form: collect every visible field label, placeholder and upload
   prompt after `read_page`, then
   `echo '<JSON list of labels>' | .venv/bin/careeros safety fields <job_id> --labels-json - --page-url <current url>`.
   Exit 3 (block): SSN / national ID, date of birth, bank numbers, passport or ID uploads, driver's
   license, mother's maiden name (allowed only once status is `offer`); any fee or card number; passwords,
   security questions or codes for another account (creating a password or entering an emailed code on the
   ATS's own domain is normal); remote-access software. Work-authorization questions are normal.
3. A redirect to a domain other than the apply URL's, the company's or a known ATS: stop and run
   `careeros safety flag "<company>" --domain <host> --confidence medium --reason "redirect to <host>" --evidence <url>`.

On exit 3 from step 2:
1. Do not enter anything further.
2. `s.step("safety_gate", False, "<first flag line>")`, save the session, print `RESULT` with
   `outcome: failed`, reason `safety block: <codes>`, then close the tab.

The user reviews the item by hand; the gate is never overridden from inside this skill (clearing a
company is `careeros safety clear <company> --note ...`, run by the user).

Start the session record:

```python
from careeros.apply.session import ApplySession
s = ApplySession.start(job_id, ats, apply_url=url, tier=tier, auto_submit=auto_submit,
                       resume_version=resume_json["meta"]["resume_version"])
```

Log every browser step with `s.step(action, ok, note)`. Save with `s.save(job_dir)` at the end of every
path below, including errors. Set status with
`.venv/bin/careeros job status <job_id> <applied|needs_review> --note "<reason>" --lock-token <token>` (updates
`status.json` and the tracker row together; every "status needs_review" / "status applied" below means
this command).

### 1c. Known hurdles (before opening the form)

Run `.venv/bin/careeros learn list --ats <ats> --company "<company>" --json` and read every lesson's `text`
as an instruction for this session (general lessons + this ATS + this company; `profile/apply_lessons.yaml`).
They record what an earlier session had to work around (an upload that must finish before Next, a hidden EEO
toggle, a page that needs a portfolio link). Follow them; they never override a hard rule below.

## 2. Open and detect

1. `tabs_create_mcp` then `navigate` to `apply_url`. Wait for load. Screenshot → `s.shot(s.next_screenshot_path(job_dir, "landing"))`.
2. Confirm the ATS from the loaded URL and DOM (adapters.md "Detecting the ATS"). If it differs from
   `posting.ats`, use the detected one and recompute `auto_submit`.
3. Run the bot-detection scan (adapters.md). Positive → section 6.

## 2a. Login (when the ATS asks to sign in)

Logins come only from the credentials store (`.venv/bin/careeros creds get`, file `paths.credentials`, default
`~/.careeros/credentials.yaml`, outside the repo). Site key = the ATS (`workday`, `greenhouse`, `lever`, `ashby`) or
a per-tenant key the candidate chose (`.venv/bin/careeros creds list` shows them, no secrets).

1. `.venv/bin/careeros creds get <site> --json` → `username`, `notes`, `has_password`. Unknown site or `has_password: false`
   → STOP, Action Item type `laptop_required` ("add a login: `.venv/bin/careeros creds set <site> --username ...`"), needs laptop.
2. Type the username. For the password field only: `.venv/bin/careeros creds get <site> --reveal` and type its output
   straight into the field. Never print, echo, quote or summarise it; never put it in `record_field`,
   `--answers-json`, `s.step`, `log.md`, `posting.json`, `status.json`, screenshots taken with it visible
   (mask the field first) or the RESULT line. Credentials are never copied into `data/jobs/` or `profile/`.
3. Login rejected, MFA or a one-time code → STOP (section 6 rules), Action Item; never retry more than once.

## 3. Fill

Follow the ATS flow in `adapters.md` exactly. Sources for values:

- Identity: `profile/master.yaml: identity` (split name on first space for first/last).
- Résumé: `file_upload` with `<job_dir>/resume.pdf`. After upload, verify the filename is shown. Two
  failures → Action Item type `other` "file upload failed", status needs_review, stop.
- Cover letter: paste `cover_letter.txt` into the manual-entry textarea; upload `cover_letter.pdf`
  only where no textarea exists. Skip entirely when tier says `if_required` and the field is optional.
- Every other field, by label text:

```python
from careeros.apply.questions import answer_for, classify_question
hit = answer_for(label, "profile/standard_answers.yaml", required=<field is marked required>, company=<posting company>)
```

  `company=` tries the answers learned for this company (`company_answers` block) before the general list.

  `answer_for` minimizes personal data: an optional street-address field stays blank; only a required
  one gets the street. Phone and email are the only other contact data given. A `sensitive` label never
  gets an answer (the field gate above already stopped the run).

  - hit with an answer → fill it. Apply the `note` rules from the YAML (referral name from
    Contacts tab; `previously_applied` = Yes if tracker shows this company applied).
  - hit with `None` answer (salary): if the control is a dropdown of ranges, pick the lowest bucket
    whose floor >= `config/targets.yaml: candidate.salary_dropdown_floor_usd`; if that key is missing,
    or the control is freeform, STOP → Action Item type `salary`, status needs_review.
  - no hit: `classify_question(label)`:
    - `eeo` → section 4.
    - `legal` → STOP, Action Item type `question` ("legal question not in standard answers: <label>"). Never guess.
      Every `question` / `salary` Action Item's text must contain the exact form question verbatim (`<class>:
      <question>` or `... : <label>`): `careeros action done <id> --answer "<text>"` learns the answer from it.
    - `essay` / `unknown` / `standard` → look up the `answers.json` entry (a JSON list) whose `question`,
      whitespace-collapsed and lower-cased, equals the label normalized the same way. Missing → run
      `/answer-question <job_dir> "<label>" --limit <maxlength>` per
      `.claude/skills/answer-question/SKILL.md`. If it returns `needs_review` with a non-null `answer`
      (class `standard` / `essay`, e.g. tier A flags every answer) and `auto_submit` is false (assisted mode,
      `CAREEROS_AUTO_SUBMIT=0`): fill that best-effort answer, keep `needs_review: true` on its `answers.json`
      entry and list the question in the "Review & submit" Action Item text (section 5) so the candidate checks
      it before submitting. Otherwise (`answer` null: class `sensitive`, `salary_freeform` or `unknown` with
      nothing to fill; or `auto_submit` true) → STOP, leave the field blank, screenshot, Action Item type
      `question`, status needs_review.
  - Respect `maxlength`; an over-limit answer is a STOP (type `question`).
- After filling any field, record what went in: `s.record_field(label, value, source)` with `source` one of
  `profile`, `standard`, `eeo`, `essay`, `salary`, `upload` (for uploads the value is the file name). These
  values are kept in the as-submitted snapshot (section 5). Secrets are never recorded: do not pass a
  password (e.g. the Workday account password), a verification or one-time code, a security question
  answer, a token or an API key to `record_field` or `--answers-json`, and never write them in `s.step`
  notes, `log.md` or the RESULT line. As a backstop, `record_field` and `freeze` store `<redacted>` for any
  label matching `careeros.apply.session.is_secret_label`.
- After each page/step in multi-page flows: screenshot, `s.step`.

## 4. EEO

Fill only from `profile/standard_answers.yaml: eeo`. Each field is `{answer, prefer?, match_not?}`
(a bare string is treated as `answer`). For every EEO control, read the option labels the form
offers, then:

```python
from careeros.apply.questions import load_eeo_answers, select_eeo_option
choice = select_eeo_option("race_ethnicity", offered_labels, load_eeo_answers("profile/standard_answers.yaml"))
```

Field names: `gender`, `hispanic_latino`, `race_ethnicity`, `veteran`, `disability`. Map a form label
to a field by keyword (gender; hispanic/latino; race/ethnicity; veteran; disability). `prefer` is picked
when the form offers it (for example "Middle Eastern or North African"), else `answer`; labels match
case-insensitively by prefix, then substring. `None` → leave blank and
`s.step("eeo_<field>", ok=True, note="no matching option, left blank")`. Never pick a demographic
value the helper did not return.

## 5. Pre-submit self-check and submit

1. Scroll the form top to bottom, full-page screenshot → `s.shot(..., "prefill_review")`.
2. Self-check, via `read_page` / `javascript_tool` (read-only):
   - every `required` / `*` field has a value;
   - the résumé field shows `resume.pdf` (or the renamed file) and the cover letter field has text or file;
   - no field contains `[FILL IN`, `TODO`, `lorem`, `{{`, `(((`;
   - name, email, phone equal the profile values exactly;
   - the bot scan is still clean.
   Any failure → fix once if trivial (retype a value); else STOP, Action Item type `review`.
3. If `not s.can_click_submit()` (tier A, `CAREEROS_AUTO_SUBMIT=0`, assisted ATS, or already clicked): status `needs_review`,
   Action Item type `review`, priority H for tier A, `what`: "Review & submit <company> <role>. Form is
   filled in the open tab. Screenshot: <prefill_review path>" plus, when any `answers.json` entry has
   `needs_review: true`, "Check answers: <question labels>", `link`: apply_url. Leave the tab open.
   `s.finish("staged", reason="assisted: review & submit")` (outcome `staged` = filled, nothing clicked;
   its `status` is `needs_review`). Go to 7. When the user submits and
   runs `careeros job status <job_id> applied --lock-token <token>`, the snapshot is frozen then (reason `assisted_stop`, with
   the values recorded here), so do not freeze on this path.
4. Auto-submit: `s.mark_submit_clicked(job_dir)` (writes `submit_clicked: true` to `apply_session.json`
   before anything else; it raises if any earlier session already clicked), then one click on the submit control from adapters.md.
5. Wait and poll for a success signal (adapters.md "Success detection", up to 20 s).
   - Success: screenshot → `s.shot(..., "confirmation")`; `s.finish("submitted", confirmation_text=...)`;
     freeze what went out: `from careeros.apply.snapshot import freeze; freeze(job_dir, session=s)`
     (copies résumé, cover letter, answers, posting and the recorded field values into
     `<job_dir>/submitted/<stamp>/`, read-only; never overwrites an earlier one); then status `applied` (`careeros job status <job_id> applied --lock-token <token>`), then
     `.venv/bin/careeros tracker upsert <job_id> --field DateApplied=today --field ATS=<ats> --field ResumeVersion=<meta.resume_version> --field Status=applied --lock-token <token>`.
   - Validation error shown: read it. Do NOT click submit again. `s.finish("needs_review", reason="validation: <text>")`,
     Action Item type `review` with the error text. Status needs_review.
   - No signal and no error after 20 s: run the bot scan; positive → section 6; else
     `s.finish("needs_review", reason="no confirmation detected")`, Action Item type `review` ("check whether
     the application went through before resubmitting"), status needs_review.

## 6. CAPTCHA / bot detection

1. Screenshot → `s.shot(..., "bot_detection")`.
2. Append or update the entry in `src/careeros/apply/detection.yaml` (`entries:`), fields per the file
   header, `skip_auto: true`.
3. `s.finish("blocked", reason="bot_detection:<type>", action_item=<the item>)`.
4. Action Item type `bot_detection`, priority H, `what`: "<type> at <company> (<ats>). Form filled up to
   <last ok step>. Open <apply_url>, complete the check, submit. Materials in <job_dir>.", `link`: apply_url.
5. Status `needs_review`. Leave the tab open.

## 7. Always, last

1. `s.save(job_dir)` (writes `apply_session.json`, appends to `log.md`).
2. Append any Action Item to the tracker `Action Items` tab:
   `.venv/bin/careeros action add "<what>" --type <type> --job <job_id> --priority <H|M> --link <apply_url> --needs laptop`
   (review/submit items need the laptop; use `phone` only for items answerable by text).
3. Run the status command from section 1 with the final outcome: `applied` on submitted, else `needs_review`.
4. Close the tab only on `submitted` or `failed`; keep it open for `needs_review` / `blocked`.
5. Learn from the session. For each hurdle this run hit and worked around (a control that needed a wait, a
   step adapters.md does not describe, a field that needed a non-obvious source), record it once:
   `.venv/bin/careeros learn lesson "<one factual line, no personal data>" --ats <ats> [--company "<company>"] --job <job_id>`.
   Only genuine, reusable hurdles (not "filled the form"); skip anything already in the Known hurdles list.
   Add the same lines to the RESULT as `learned: [...]` (empty list when nothing was learned).
6. Print exactly one final line: `s.result_line()` → `RESULT: {"job_id":..., "outcome":..., "status":..., "learned": [...], ...}`.

## Hard rules

- Never click submit twice. Never retry after a validation error without a human.
- Never answer legal, salary, or demographic questions outside `standard_answers.yaml`.
- Never invent text. Anything missing is an Action Item, not a guess.
- Never use "Apply with LinkedIn" or any LinkedIn automation.
- Never create accounts with invented passwords; Workday account creation is an Action Item unless `WORKDAY_PASSWORD` is set.
- Logins come only from `.venv/bin/careeros creds get` (section 2a); never print a password or store it in job data.
- One job per invocation. One tab per job.
