# ATS adapters (procedural spec for `/apply-job`)

The applier is Claude Code driving Chrome through the `mcp__claude-in-chrome__*` tools. There is no
Selenium; an "adapter" here is the field map and the click order the skill follows for one ATS, plus
the checks it must run at each step. Python helpers: `questions.py` (answer matching),
`session.py` (audit record), `detection.yaml` (bot-detection registry).

Tool vocabulary used below:

| Tool | Used for |
|---|---|
| `tabs_create_mcp` / `navigate` | open `apply_url` in a fresh tab |
| `read_page` (interactive) / `find` | locate fields by label, id, aria |
| `form_input` | set text, select, checkbox, radio |
| `file_upload` | résumé / cover letter PDFs |
| `computer` (click, screenshot) | buttons, scroll, screenshots |
| `get_page_text` | confirmation and error text |
| `javascript_tool` | read-only probes only (querySelector counts, iframe src list); never to submit |

Global rules, every ATS:

1. One tab per application. Close it when the session ends.
2. Screenshot before any click that changes state (upload, next page, submit) and after it.
   Save under `data/jobs/<id>/screenshots/` via `ApplySession.next_screenshot_path()`.
3. Never click a submit button twice. `ApplySession.can_click_submit()` guards this.
4. Never type anything not in `profile/master.yaml`, `profile/standard_answers.yaml`,
   `data/jobs/<id>/answers.json`, or `cover_letter.txt`.
5. Run the bot-detection scan (below) after page load, after every upload, and after submit.
6. Any `needs_review` path: screenshot, `ApplySession.finish("needs_review", ...)`, Action Item, stop.

---

## Detecting the ATS from `apply_url`

| Pattern | ATS | Mode (`config/targets.yaml: safety`) |
|---|---|---|
| `boards.greenhouse.io/<co>/jobs/<id>`, `job-boards.greenhouse.io/<co>/jobs/<id>`, `<co>.greenhouse.io` | greenhouse | auto |
| `jobs.lever.co/<co>/<uuid>` (append `/apply` if missing) | lever | auto |
| `jobs.ashbyhq.com/<co>/<uuid>` (append `/application` if missing) | ashby | auto |
| `<co>.wd1.myworkdayjobs.com`, `*.myworkdayjobs.com`, `*.myworkdaysite.com` | workday | assisted |
| `*.icims.com` | icims | assisted |
| `*.taleo.net` | taleo | assisted |
| `*.smartrecruiters.com`, `jobs.smartrecruiters.com` | smartrecruiters | assisted |
| `*.jobvite.com` | jobvite | assisted |
| `*.successfactors.com`, `*.sapsf.com` | successfactors | assisted |
| anything else | custom | assisted |

Also check `posting.json: ats` (scout already knows). If URL and posting disagree, trust the URL after
the page loads (companies embed Greenhouse forms on their own domains; look for an iframe with
`src*="greenhouse.io"` or `grnh.se` and switch to that frame).

`assisted` mode: fill everything you safely can, stop before the final submit, Action Item
"review & submit" with the screenshot. Never auto-submit outside `safety.auto_submit_ats`.

---

## Bot-detection and CAPTCHA scan

Run this probe (read-only) at each checkpoint:

```
javascript_tool:
  ({
    iframes: [...document.querySelectorAll('iframe')].map(f => f.src).filter(Boolean),
    captcha: !!document.querySelector('.g-recaptcha, .h-captcha, [data-sitekey], .cf-turnstile, #turnstile-widget, iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="turnstile"], iframe[src*="challenges.cloudflare.com"]'),
    title: document.title,
    url: location.href,
    bodyStart: document.body.innerText.slice(0, 400)
  })
```

Treat as `bot_detection` (config `safety.pause_on: captcha | bot_detection_suspected`) if any of:

- `captcha` true, or any iframe src containing `recaptcha`, `hcaptcha`, `turnstile`, `challenges.cloudflare.com`, `arkoselabs`, `funcaptcha`, `perimeterx`, `px-cloud`, `datadome`.
- Page text or title matches (case-insensitive): `verify you are human`, `checking your browser`,
  `just a moment`, `attention required`, `access denied`, `unusual traffic`, `are you a robot`,
  `security check`, `press and hold`, `enable javascript and cookies to continue`, `ray id`.
- URL changed to a domain other than the ATS or company domain (an "unusual redirect"), or to a
  path containing `/challenge`, `/cdn-cgi/`, `/blocked`, `/captcha`.
- Submit click produced no navigation, no confirmation text, and no visible validation error
  within 15 s (silent rejection). Check twice, 5 s apart, before concluding.
- HTTP 403/429 in `read_network_requests` for the submit call.

Invisible reCAPTCHA v3 (`grecaptcha` present, no visible widget) is normal on Greenhouse and Lever
and does not by itself count. Only pause when a visible challenge appears or the submit is rejected.

On detection:

1. Screenshot.
2. Append to `src/careeros/apply/detection.yaml` (`entries:`): company, domain (host + first path
   segment), ats, detection_type, first_seen/last_seen (ISO UTC), count, `skip_auto: true`, job_id, notes.
   If the company/domain already exists: bump `count`, `last_seen`, append job_id.
3. `ApplySession.finish("blocked", reason="bot_detection:<type>", action_item=...)`.
4. Action Item type `bot_detection`, priority H, `what`: "CAPTCHA/bot check on <company> <ats>. Form
   is filled up to <step>. Open <apply_url>, solve, submit. Materials: resume.pdf, cover_letter.txt,
   answers.json". Tracker status `needs_review`.

Before starting any job: if `detection.yaml` has an entry with `skip_auto: true` for this company or
domain, do not open the browser. Create the same Action Item with the prepared materials and stop.

---

## Success detection (all ATS)

After submit, wait up to 20 s, polling `get_page_text` every 4 s. Success when the page text or URL
matches one of:

- Text: `Thank you for applying`, `Thanks for applying`, `Application submitted`, `Your application
  has been submitted`, `Application received`, `We've received your application`, `Thank you for your
  application`, `successfully submitted`, `You have applied`, `Thank you for your interest` (only when
  the form is gone).
- URL: Greenhouse `?confirmation=true` or `/confirmation`; Lever `/thanks`; Ashby `/application/submitted` or
  page shows "Application submitted" card; Workday "My Applications" page listing the job.
- DOM: the form element that held the submit button no longer exists and no error banner is shown.

If none within 20 s: treat as silent rejection (see bot scan), outcome `needs_review`, never re-click.
Record the matched text in `ApplySession.finish(confirmation_text=...)` and screenshot the page.

---

## Greenhouse

URL: `https://boards.greenhouse.io/<co>/jobs/<id>` or `https://job-boards.greenhouse.io/<co>/jobs/<id>`.
Newer boards ("job-boards") are a React form; classic boards are a plain form `#application_form`.
Both expose the same logical fields.

Flow:

1. Open URL. If the description page has an "Apply" button (`#apply_button`, or text "Apply for this
   job" / "Apply now"), click it; the form is on the same page under `#application`.
2. Bot scan.
3. Identity (`form_input` by id or label):
   - `#first_name` / label "First Name"
   - `#last_name` / label "Last Name"
   - `#email` / label "Email"
   - `#phone` / label "Phone" (`identity.phone`, formatted as written in the profile)
   - Location: `#job_application_location` or label "Location (City)"; type the city from
     `identity.location`, wait for the autocomplete, pick the first entry whose city and state match it
     (none matches → leave blank and note it in the review Action Item).
4. Résumé: label "Resume/CV". Options appear as "Attach" (`input[type=file]`, id `resume` or
   `input[name="job_application[resume]"]`), "Dropbox", "Google Drive", "Enter manually".
   Use `file_upload` on the file input with `data/jobs/<id>/resume.pdf`. Verify the filename appears
   next to the field (text `resume.pdf` or the chosen name). If upload fails twice: "Enter manually"
   and paste `resume.txt` into the textarea; note it in the session (`file_upload_failed` is a
   pause reason only when both fail).
5. Cover letter: label "Cover Letter". Prefer "Enter manually" and paste `cover_letter.txt`
   (`textarea#cover_letter_text`), since the text version is what recruiters see inline. Upload
   `cover_letter.pdf` instead if manual entry is absent.
6. Standard fields often present: "LinkedIn Profile" (`#job_application_answers_attributes_*_text_value`
   with label text), "Website", "GitHub", "How did you hear about us?". Match via
   `questions.match_standard_answer(label)`.
7. Custom questions: each in a `.field` (classic) or `div[class*="field"]` / `label + input|select|textarea`
   (React). Read the label text (strip `*`). For each:
   - `match_standard_answer` hit (entries tried in file order, first hit wins) → fill. `select` elements: pick the option whose text equals the
     answer (case-insensitive) or, for Yes/No, starts with it. React selects: click the control,
     type the answer, press Enter, then verify the displayed value.
   - Answer with `null` (salary) → needs_review.
   - `classify_question` = `eeo` → skip here; handled in step 8.
   - Otherwise → the `answers.json` entry (a list, written by `answer-question`) whose normalized `question` equals the normalized label.
     Missing → run `/answer-question` now; `needs_review` result → stop.
   - Char limits: read `maxlength`; if the answer exceeds it, stop (needs_review, "answer over limit").
8. EEO: `#eeoc_fields` (classic) or section titled "Voluntary Self-Identification" / "Equal
   Employment Opportunity". Selects: `#job_application_gender`, `#job_application_hispanic_ethnicity`,
   `#job_application_race`, `#job_application_veteran_status`, `#job_application_disability_status`.
   Read each select's option labels, then `select_eeo_option(field, labels, eeo)` (questions.py):
   `prefer` first if offered, else `answer`, prefix then substring, case-insensitive. Leave blank
   when it returns None (EEO is voluntary) and note it in the session.
9. Pre-submit self-check (see SKILL.md), full-page screenshot.
10. Submit: `#submit_app` (classic) or `button[type=submit]` with text "Submit application".
    Greenhouse shows inline errors in `.field-error` / red text; if any appear after the click,
    read them, fix once if it is a standard field, else needs_review. Do not click submit again
    unless the first click produced a validation error and no submission (session `submit_clicked`
    still blocks a second click; in that case finish `needs_review` with reason "validation error").
11. Success: URL gains `?confirmation=true` or text "Thank you for applying". Screenshot.

Known quirks: some boards require the location autocomplete to be selected, not typed. The résumé
upload input is hidden; `file_upload` targets it directly. Security questions ("What is 2+2?") are
custom questions; treat them as `unknown` → needs_review.

---

## Lever

URL: `https://jobs.lever.co/<co>/<uuid>/apply`. Plain form `#application-form`, POST to `/apply`.

Flow:

1. Open URL (force `/apply` suffix). Bot scan.
2. Résumé first: `input[name="resume"]` (label "Resume/CV", accepts PDF). Lever parses it and
   auto-fills name/email/phone after upload; wait 5 s, then overwrite any wrong value.
3. Identity: `input[name="name"]` (full name from `identity.name`), `input[name="email"]`,
   `input[name="phone"]`, `input[name="org"]` (current company: `standard_answers: current_employer`),
   `input[name="urls[LinkedIn]"]`, `input[name="urls[GitHub]"]`, `input[name="urls[Portfolio]"]`
   (leave blank while `identity.website` is null), `input[name="urls[Other]"]` blank.
4. Cover letter: `textarea[name="comments"]` (label "Additional information"). Paste `cover_letter.txt`
   only when the posting or tier requires a cover letter; otherwise leave blank.
5. Custom cards: `.application-question` blocks, inputs named `cards[<id>][field<n>]`. Label text
   is in `.application-label`. Same matching rules as Greenhouse step 7. Dropdowns are native
   `select`; checkboxes are `input[type=checkbox]` groups (pick by option label).
6. EEO: `.application-additional` section (`eeo[gender]`, `eeo[race]`, `eeo[veteran]`,
   `eeo[disability]` selects). Fill via `select_eeo_option` from `standard_answers.yaml: eeo` only.
7. Consent: `input[name="consent[marketing]"]` leave unchecked; a required GDPR/privacy consent
   checkbox is fine to check (it is disclosure, not a claim).
8. Pre-submit self-check, screenshot.
9. Submit: `button#btn-submit` (text "Submit application"). Lever runs reCAPTCHA invisibly; a visible
   challenge here is `bot_detection`.
10. Success: URL `/thanks` or text "Application submitted" / "Thank you for applying". Screenshot.

Known quirks: Lever rejects phone numbers with letters; keep `identity.phone` digits and dashes only. If the posting has
"Apply with LinkedIn", ignore it (never auto-LinkedIn).

---

## Ashby

URL: `https://jobs.ashbyhq.com/<co>/<uuid>/application`. React form, all fields labelled via
`<label for>` and `aria-label`; ids are generated, so select by label text.

Flow:

1. Open URL. Bot scan.
2. "Autofill application from resume": if present (button text "Autofill from resume" or the
   résumé dropzone at the top), upload `resume.pdf` there first via `file_upload` on the hidden
   `input[type=file]`. Wait for the spinner to finish (up to 20 s), then verify every autofilled
   value against the profile and overwrite mismatches. If autofill is absent, upload at the
   "Resume" field.
3. Identity by label: "Name" (full name) or "First name"/"Last name"; "Email"; "Phone";
   "LinkedIn" / "LinkedIn Profile"; "GitHub" / "GitHub Profile"; "Website" / "Portfolio" (blank);
   "Location" / "Current location" (type, choose the first matching suggestion when a list appears).
4. Cover letter: label "Cover Letter" (upload) or a long-text field "Why do you want to work at
   ...?" style. Upload `cover_letter.pdf` where a file field exists; paste `cover_letter.txt` where
   a textarea exists. Never both.
5. Custom questions: each question is a `div` with a `label`/`legend` and one control. Ashby types:
   short text, long text (`textarea`), select (custom dropdown: click, type, Enter, verify),
   multi-select (checkbox list), Yes/No (radio, `role="radio"`), number, date, file.
   Same matching rules as Greenhouse step 7. For `role="radio"` groups use `find` on the option
   label then `computer` click; confirm `aria-checked="true"`.
6. EEO: section "Voluntary Self-Identification" / "Demographic Survey". Fill only from
   `standard_answers.yaml: eeo` via `select_eeo_option` (prefix/substring, case-insensitive); None →
   leave blank.
7. Pre-submit self-check, screenshot.
8. Submit: `button[type=submit]` with text "Submit Application". Ashby shows field errors inline
   ("This field is required") and scrolls to the first one; handle as Greenhouse step 10.
9. Success: text "Application submitted" / "Thank you for applying" or the form is replaced by a
   confirmation card. Screenshot.

Known quirks: Ashby sometimes needs a real `click` on the field before `form_input` registers a
React change; if a value does not stick, click then retype. hCaptcha may appear on submit for some
boards → `bot_detection`.

---

## Workday (assisted only)

URL: `https://<co>.wd<N>.myworkdayjobs.com/<site>/job/<location>/<slug>_<req>` → "Apply" →
`/apply/applyManually` or `/apply/autofillWithResume`. Multi-page; every page is a separate submit.
`auto_submit` is always false here (`safety.assisted_ats`). The goal is to get as far as the
Review page, then hand off.

Flow:

1. Open URL, click "Apply". A modal offers "Autofill with Resume", "Apply Manually", "Use My Last
   Application". Pick "Autofill with Resume"; upload `resume.pdf`.
2. Account: Workday requires sign-in per company tenant. If a "Create Account" form appears:
   fill email + a password from the `WORKDAY_PASSWORD` environment variable if set, else stop with
   Action Item `account_creation_email_verify` ("Create Workday account at <host>, then rerun").
   If a verification email step appears → same Action Item (config `pause_on`). Never invent a
   password; never reuse the Gmail password.
3. "My Information" page: name, address (`standard_answers: address`; if a full street address is
   required and only city/state/zip is on file → stop, Action Item "full street address needed"),
   email, phone (type "Mobile"), "How did you hear about us" (standard answer), "Previously worked
   here" (standard `previously_applied`, override to Yes if the tracker has this company as applied).
   Click "Save and Continue".
4. "My Experience" page: autofill usually populates work history and education from the résumé.
   Verify each entry against `profile/master.yaml` (company, title, dates); delete anything invented
   by the parser; do not add entries not in the profile. Add "Websites" (LinkedIn, GitHub). Upload
   résumé again in the "Resume/CV" panel if empty. Save and Continue.
5. "Application Questions" page(s): one or more pages of custom questions. Same matching rules as
   Greenhouse step 7; Workday controls are `button[aria-haspopup="listbox"]` dropdowns (click, choose
   the option text), radios, text inputs. Unmatched → needs_review with the page name in the note.
6. "Voluntary Disclosures": EEO via `select_eeo_option` from `standard_answers.yaml: eeo` only. "Self Identify" (disability
   form) requires name + date: fill name, leave date for the candidate if the form insists on a signature.
7. "Review" page: screenshot the full page (scroll and capture each viewport). STOP here.
   `ApplySession.finish("needs_review", reason="workday review page reached")`, Action Item type
   `review`, `what`: "Workday application ready at Review page for <company> <role>. Open <url>,
   check the Review page against screenshots, click Submit." Status `needs_review`.

Workday sessions expire after ~30 min idle; note the time in the Action Item.

---

## Other assisted ATS (iCIMS, Taleo, SmartRecruiters, Jobvite, SuccessFactors, custom)

No field map yet. Procedure: open, bot scan, fill anything whose label matches a standard answer or
identity field, upload résumé where an obvious file field exists, screenshot, stop before submit,
Action Item "review & submit". Log the field labels you saw in `apply_session.json` steps so a map
can be written later.

---

## Per-ATS summary

| ATS | Detect | Submit control | Success signal | Resume field |
|---|---|---|---|---|
| greenhouse | `greenhouse.io/<co>/jobs/` | `#submit_app` / "Submit application" | `?confirmation=true`, "Thank you for applying" | `input[type=file]` under "Resume/CV", or "Enter manually" |
| lever | `jobs.lever.co/<co>/<uuid>` | `#btn-submit` "Submit application" | `/thanks`, "Application submitted" | `input[name=resume]` |
| ashby | `jobs.ashbyhq.com/<co>/<uuid>` | "Submit Application" | "Application submitted" card | autofill dropzone or "Resume" |
| workday | `*.myworkdayjobs.com` | never (assisted) | "My Applications" list | "Autofill with Resume" |
