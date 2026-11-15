---
name: job-alerts
description: Turn LinkedIn job-alert emails in Gmail into company boards for scout. Reads the alert emails (user signs in to Gmail themselves), extracts the companies, finds their Greenhouse/Ashby/Lever boards with `careeros company find-board`, verifies each hit, adds them to config/companies.yaml and runs scout. Use for "job alerts", "LinkedIn alerts", or refreshing companies from email.
---

# job-alerts

LinkedIn is never automated (repo hard rule). This flow only reads emails LinkedIn already sent to the user, and
uses them to find the companies' own job boards. Repeat it weekly.

## One-time setup (user)

1. On LinkedIn, create job alerts for their target roles and locations, delivery **email** (daily or weekly).
2. In Gmail, create a filter: from `jobalerts-noreply@linkedin.com` → apply label `job-alerts` (any label name;
   ask which). Tick "also apply to matching conversations".

## Read the alerts (Claude desktop browser pane)

1. **user**: open Gmail in the browser pane and sign in themselves. Never ask for or type their password, never
   read or export cookies.
2. Open the label: `https://mail.google.com/mail/u/0/#label/<label>` (spaces in the label become `+`).
3. Collect thread ids page by page with page JavaScript: visible rows `tr.zA`, each holding an element with
   `data-legacy-thread-id`. Go to the next page (`#label/<label>/p2`, `p3`, ...) until a page adds no new ids or
   the rows are older than about 10 weeks (older companies have usually filled the role).
4. Read each thread with a same-origin fetch from the Gmail tab:
   `fetch('/mail/u/0/?ik=' + GLOBALS[9] + '&view=pt&search=all&th=' + id).then(r => r.text())`.
   Strip tags with string replaces (`<[^>]+>` → newline) and decode entities; `DOMParser` and `innerHTML` are
   blocked there by Trusted Types. Keep only the email date and the plain text.
5. Parse job lines: a job is a title line directly followed by a `<Company> · <Location>` line (middle dot).
   Keep title, company, location. Drop emails older than ~10 weeks.
6. **user**: sign out of Gmail in the browser pane when done, unless they want to stay signed in there.

No browser pane? Use a Gmail connector if one is connected: search `label:<label> newer_than:70d` and parse the
same lines from each message body.

## Turn companies into boards

1. Dedupe companies (case-insensitive) and drop any already in `config/companies.yaml` (`boards:`, `blocklist`).
   Write one name per line to a scratch file (not in the repo), e.g. `/tmp/alert-companies.txt`.
2. `.venv/bin/careeros company find-board --file /tmp/alert-companies.txt`
3. Verify every hit before adding it. Generic names often match a different company with the same slug: fetch the
   board's job titles (the printed board URL, or `--json`) and keep the hit only if at least one alert title for
   that company, or a clearly matching team, appears there. Report the ones dropped and why.
4. Add the verified lines under `boards:` in `config/companies.yaml`, keeping its comments, under a
   `# --- from LinkedIn alerts <date> ---` comment.
5. `.venv/bin/careeros scout --sync`, then say how many new jobs came from these boards.

Companies with no Greenhouse/Ashby/Lever board (Workday and custom sites) can't be scouted: list them for the
user as "apply on their site by hand" and stop there.

## Report

Threads read, date range, companies found, boards added (verified), boards rejected (same name, other company),
no-board companies, new jobs from scout.
