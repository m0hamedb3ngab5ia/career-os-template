---
name: apply-job
description: Submit (or stage for review) one prepared application through Chrome. Input is a job dir under data/jobs/. Use during an apply session after /prepare-job has produced resume.pdf, cover_letter.txt, answers.json and a passing qa.json.
---

# /apply-job <job_dir>

Drive the ATS form in Chrome for one job, following `src/careeros/apply/adapters.md`. Auto-submit
only when the tier and ATS allow it; otherwise stop before submit and hand off with an Action Item.
Never type anything that is not in the profile, standard answers, answers.json, or cover_letter.txt.

Argument: `data/jobs/<job_id>` (absolute or repo-relative). Everything below refers to files in it.

## Setup guard (before anything else)

Run `.venv/bin/careeros doctor --quiet` first. If it exits nonzero, STOP before opening a browser:
print its FAIL lines and a `RESULT` with `outcome: failed`, reason `setup: careeros doctor failed`.
Never submit with the example candidate's data (Alex Example) or a half-configured profile.

## 0. Load tools

`ToolSearch` once: `select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__read_page,mcp__claude-in-chrome__find,mcp__claude-in-chrome__form_input,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__file_upload,mcp__claude-in-chrome__get_page_text,mcp__claude-in-chrome__javascript_tool,mcp__claude-in-chrome__read_network_requests,mcp__claude-in-chrome__tabs_close_mcp`

Python runs with `.venv/bin/python` from the repo root.

## 1. Preconditions (all must hold, else stop with the reason)

Read `posting.json`, `score.json`, `status.json`, `qa.json`, `config/targets.yaml`,
`profile/master.yaml`, `profile/standard_answers.yaml`, `src/careeros/apply/detection.yaml`.

| Check | Source | On fail |
|---|---|---|
| no earlier submit: `ApplySession.already_submitted(job_dir)` is False | `apply_session.json` | outcome failed, reason "submit already clicked in an earlier session; check the ATS by hand"; Action Item type `review`; no browser |
| status is `queued` (or `prepared`); `needs_review` only when the effective tier (row below) is A, and then `auto_submit` is forced off (staging for the candidate) | `status.json` | print `RESULT` with `outcome: failed`, reason "status <x>"; no browser |
| `qa.json` top-level `pass` is `true` and `deterministic.pass` is `true` (the qa-review schema) | `qa.json` | outcome failed, reason "qa not passed"; no browser |
| `resume.pdf` exists | job dir | if only `resume.tex`: Action Item type `other` "no PDF; install LaTeX engine (`brew install tectonic`) then rerun /prepare-job"; outcome failed |
| `cover_letter.txt` exists when tier `cover_letter: always`, or posting requires one | job dir, targets.yaml | outcome failed, reason "cover letter missing" |
| detected ATS (adapters.md table, from `posting.apply_url` or `url`) | posting.json | record in session |
| tier from `score.json: tier`; the tracker `Override` column wins if set: read it with `.venv/bin/careeros tracker show <job_id> --json` (`Override` key; `A`/`B`/`C` replace the tier, `manual` or `skip` = no auto-submit) | score.json, tracker | if the command fails: `auto_submit` = false |
| `auto_submit` = tiers[tier].auto_submit AND ats in `safety.auto_submit_ats` AND `safety.json: auto_submit_allowed` (from `careeros safety check`, section 1b: `auto_submit_allowed` = allowlisted ATS on its own or the company's domain, reached from the company's board, no flags) | targets.yaml, safety.json | if false: proceed in assisted mode (stop before submit) |
| company not in `detection.yaml` with `skip_auto: true` | detection.yaml | Action Item `bot_detection` "known bot detection at <company>; apply by hand with prepared materials"; status needs_review; no browser |
| daily cap: `.venv/bin/careeros tracker applied-count --days 1` (all companies, today) < `volume.max_applications_per_day` x `season_multiplier[month]` | tracker | outcome failed, reason "daily cap" |
| company cap: `.venv/bin/careeros tracker applied-count "<company>" --days 90` < `volume.max_per_company_per_90_days` | tracker | outcome failed, reason "company cap" |
| company not rejected within `same_company_cooldown_days` | `.venv/bin/careeros jobs list --json --status rejected` (same company), then that job's `status.json` history timestamp | outcome failed, reason "cooldown" |

`applied-count` prints one integer (0 when the tracker does not exist yet). Never open the workbook
directly from this skill; every tracker read/write goes through the `careeros` CLI.

### 1b. Scam / data-harvesting gate (hard stop, before any form fill)

Code: `src/careeros/safety/scam.py` (spec in `TODO.md` "Safety"). Run it after the preconditions above
and again in section 3 as soon as the form's fields are visible, before typing anything. Exit 3 is a
hard stop: never fill, never submit, never "just this once".

1. Posting gate, before opening the browser: `.venv/bin/careeros safety check <job_id>`.
   It checks the apply-URL domain (company's own or a known ATS), free-provider recruiter emails, scam
   phrases (messaging-app interviews, check deposits, buy-equipment-get-reimbursed, fees, pay in crypto),
   and the flagged registry (`data/flagged_registry.yaml`), and writes `safety.json`, including
   `auto_submit_allowed` (see the preconditions table).
2. Field gate, on every page/step of the form: collect every visible field label, placeholder and upload
   prompt after `read_page`, then
   `echo '<JSON list of labels>' | .venv/bin/careeros safety fields <job_id> --labels-json -`.
   It stops on SSN / national ID, date of birth, bank or card numbers, passport or ID uploads, driver's
   license, mother's maiden name (all allowed only once status is `offer`) and any fee (never).
3. Also stop, by hand, when a page you land on after redirects is on a domain other than the posting's
   apply URL, the company's, or a known ATS: run `careeros safety flag "<company>" --domain <host>
   --reason "redirect to <host>"`, then the steps below.

On exit 3 the CLI has already opened the `scam_suspected` Action Item (H, phone) and set the status
`needs_review`. Then:
1. Do not enter anything further.
2. `s.step("scam_gate", False, "<first flag line>")`, save the session, print `RESULT` with
   `outcome: failed`, reason `scam_suspected: <codes>`, then close the tab.

The user reviews the item by hand; the gate is never overridden from inside this skill.

Start the session record:

```python
from careeros.apply.session import ApplySession
s = ApplySession.start(job_id, ats, apply_url=url, tier=tier, auto_submit=auto_submit,
                       resume_version=resume_json["meta"]["resume_version"])
```

Log every browser step with `s.step(action, ok, note)`. Save with `s.save(job_dir)` at the end of every
path below, including errors. Set status with
`.venv/bin/careeros job status <job_id> <applied|needs_review> --note "<reason>"` (updates
`status.json` and the tracker row together; every "status needs_review" / "status applied" below means
this command).

## 2. Open and detect

1. `tabs_create_mcp` then `navigate` to `apply_url`. Wait for load. Screenshot → `s.shot(s.next_screenshot_path(job_dir, "landing"))`.
2. Confirm the ATS from the loaded URL and DOM (adapters.md "Detecting the ATS"). If it differs from
   `posting.ats`, use the detected one and recompute `auto_submit`.
3. Run the bot-detection scan (adapters.md). Positive → section 6.

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
hit = answer_for(label, "profile/standard_answers.yaml", required=<field is marked required>)
```

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
    - `essay` / `unknown` / `standard` → look up the `answers.json` entry (a JSON list) whose `question`,
      whitespace-collapsed and lower-cased, equals the label normalized the same way. Missing → run
      `/answer-question <job_dir> "<label>" --limit <maxlength>` per
      `.claude/skills/answer-question/SKILL.md`. If it returns `needs_review` → STOP, screenshot,
      Action Item type `question`, status needs_review.
  - Respect `maxlength`; an over-limit answer is a STOP (type `question`).
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
3. If `not s.can_click_submit()` (tier A, assisted ATS, or already clicked): status `needs_review`,
   Action Item type `review`, priority H for tier A, `what`: "Review & submit <company> <role>. Form is
   filled in the open tab. Screenshot: <prefill_review path>", `link`: apply_url. Leave the tab open.
   `s.finish("needs_review", reason="assisted: review & submit")`. Go to 7.
4. Auto-submit: `s.mark_submit_clicked(job_dir)` (writes `submit_clicked: true` to `apply_session.json`
   before anything else; it raises if any earlier session already clicked), then one click on the submit control from adapters.md.
5. Wait and poll for a success signal (adapters.md "Success detection", up to 20 s).
   - Success: screenshot → `s.shot(..., "confirmation")`; `s.finish("submitted", confirmation_text=...)`;
     status `applied` (`careeros job status <job_id> applied`), then
     `.venv/bin/careeros tracker upsert <job_id> --field DateApplied=today --field ATS=<ats> --field ResumeVersion=<meta.resume_version> --field Status=applied`.
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
5. Print exactly one final line: `s.result_line()` → `RESULT: {"job_id":..., "outcome":..., "status":..., ...}`.

## Hard rules

- Never click submit twice. Never retry after a validation error without a human.
- Never answer legal, salary, or demographic questions outside `standard_answers.yaml`.
- Never invent text. Anything missing is an Action Item, not a guess.
- Never use "Apply with LinkedIn" or any LinkedIn automation.
- Never create accounts with invented passwords; Workday account creation is an Action Item unless `WORKDAY_PASSWORD` is set.
- One job per invocation. One tab per job.
