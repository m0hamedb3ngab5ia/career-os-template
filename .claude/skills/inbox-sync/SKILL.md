---
name: inbox-sync
description: Sync Gmail with the job tracker. For every applied/screening/interview job, search Gmail for company mail newer than the apply date, classify (confirmation, rejection, interview_invite, assessment, offer, recruiter_outreach), update tracker status via the careeros CLI or data/sync_updates.json, push-notify and add Action Items on interviews, assessments and offers, and catch untracked recruiter outreach.
---

# inbox-sync

`$ARGUMENTS` = optional `--since <YYYY-MM-DD>` (default: 14 days ago) and optional `--job <job_id>`
to sync one job. Read-only on Gmail: never send, reply, archive, label, or delete mail.

## 0. Tool availability

- Gmail: `mcp__claude_ai_Gmail__search_threads` and `mcp__claude_ai_Gmail__get_thread`. If they are
  deferred, load both with one ToolSearch call (`select:mcp__claude_ai_Gmail__search_threads,mcp__claude_ai_Gmail__get_thread`).
  If unavailable: print `RESULT: {"skill":"inbox-sync","error":"gmail_mcp_unavailable"}` and stop.
- Push: `PushNotification` tool if present (load via ToolSearch if deferred). If absent, the Action
  Item is the notification; note `push: false` in RESULT.
- Tracker CLI: `careeros` (`.venv/bin/careeros`). Subcommands: `jobs list --status <s> --json`,
  `job status <id> <status> --note "<note>"` (updates status.json + tracker row),
  `action add "<what>" --type <t> --job <id> --link <url> --priority H|M|L --needs laptop|phone|anytime`.
  If the CLI fails, write status changes to `data/sync_updates.json` (section 5) instead.

## 1. Load active jobs

`careeros jobs list --json` (or read `data/jobs/*/posting.json` + tracker rows if the CLI fails) and
keep rows with status in `applied, screening, interview` (also `offer` for offer follow-ups). For each:
`job_id, company, title, status, date_applied, apply_url, ats`.

Derive `company_domain`: from `posting.json.url`/`apply_url` when it is the company's own domain;
for Greenhouse/Lever/Ashby URLs use the ATS sender domains instead
(`greenhouse.io`, `greenhouse-mail.io`, `lever.co`, `hire.lever.co`, `ashbyhq.com`) plus a plain
company-name search.

## 2. Search Gmail per job

Query (one search per job, newer_than in days from `date_applied` or `--since`):
`("<company>" OR from:@<company_domain> OR from:@greenhouse-mail.io OR from:@hire.lever.co OR from:@ashbyhq.com) newer_than:<n>d`
Then filter threads client-side: subject/body must mention the company name or the role title
(case-insensitive); drop newsletters/marketing (`unsubscribe` + no role mention).

Same company, several active jobs: when more than one loaded job has this company (normalized name), a
thread belongs to a job only if it names that job's role title (or its core, e.g. "Backend Engineer") or
contains its ATS job id / apply URL. A thread that matches the company but no single job is **ambiguous**:
change no status; add one Action Item (`careeros action add "Email from <company> could be for <role A> or
<role B>: <subject>" --type review --priority H --needs anytime`) and mark it processed.

`data/inbox_seen.json` maps thread id -> last processed message id (`{"<thread_id>": "<message_id>"}`;
create the file if missing; an old list-of-ids file counts as `{id: null}`). Skip a thread only when its
latest message id equals the stored one: a new reply in a known thread (interview invite after the
confirmation) is processed again. After processing, store the thread's latest message id.

For each remaining thread call `get_thread` and read the latest message from a sender other than the candidate.

## 3. Classify (first matching rule wins)

| class | signals |
|---|---|
| `offer` | "offer letter", "pleased to offer", "extend an offer", compensation package attached |
| `interview_invite` | "schedule", "interview", "phone screen", "technical screen", "onsite", calendar link (calendly, goodtime, greenhouse scheduling), "availability for a call" from recruiter |
| `assessment` | "HackerRank", "CodeSignal", "Codility", "take-home", "assessment", "coding challenge", "online test", deadline mentioned |
| `rejection` | "not moving forward", "other candidates", "decided to pursue", "unfortunately", "not selected", "position has been filled" |
| `confirmation` | "application received", "thank you for applying", "we have received your application" |
| `recruiter_outreach` | inbound from a recruiter/sourcer about a role the candidate did not apply to |
| `other` | anything else (info request, document request, survey) |

Record `{thread_id, date, from, subject, class, link}` where link = `https://mail.google.com/mail/u/0/#all/<thread_id>`.

## 4. Map to status and actions

| class | status change | action item |
|---|---|---|
| confirmation | applied -> applied (no change), note "confirmation <date>" | none |
| rejection | -> `rejected`, note with date | none (log only) |
| assessment | -> `screening` | type `review`, priority H: "Assessment from <company> for <role>, due <date if stated> — <link>" |
| interview_invite | -> `interview` | type `review`, priority H: "Interview invite from <company> (<role>) received <date> — <link>" + push |
| offer | -> `offer` | type `review`, priority H: "OFFER from <company> (<role>) <date> — <link>" + push |
| other | none | type `other`, priority M if it asks the candidate to do something (document, form, survey) |

Other applications at the same company (assessment and interview_invite): run
`.venv/bin/careeros company active "<company>" --exclude <job_id> --json`. When its `note` is non-empty
("Also active at <Company>: <role> (<status>), ... — mention these to the recruiter."), append it to the
Action Item text after the link, so the candidate tells the recruiter about the other live applications
(applied / screening / interview, or queued / prepared).

Never move a status backwards (interview -> screening) and never change a status the user set to
`withdrawn`. Multiple emails: apply the highest-ranked change (offer > interview > screening > applied > rejected... but a rejection AFTER an interview still wins by date).

Push notification (if tool exists): title `<company>: <class>`, body `<role> — <subject> (<date>)`.

Apply changes:
- Run `.venv/bin/careeros job status <job_id> <status> --note "<note>"`.
- If it fails, append to `data/sync_updates.json` (list): `{"job_id","company","status","note","source_thread","date","applied": false}`.
- Action items: `careeros action add "<what>" --type review --job <job_id> --link "<link>" --priority H --needs <laptop|phone|anytime>`
  (interview/assessment prep needs `laptop`; a scheduling reply is `phone`).

Append to `data/jobs/<job_id>/log.md`: `- YYYY-MM-DD HH:MM:SS [inbox-sync] <class> from <from> <date> -> status <new> (<thread link>)`
(format `- YYYY-MM-DD HH:MM:SS [<skill>] <message>`, local time, identical to `store.append_log`; e.g. `date '+%F %T'`).

## 5. Untracked recruiter outreach

One extra search: `(recruiter OR sourcing OR "reaching out" OR "your background" OR "open role" OR opportunity) newer_than:<n>d -from:me`
minus threads already matched to a job. For each real inbound outreach (a person, not a job-alert
newsletter): `careeros action add "Recruiter outreach: <name> at <company> re <role/subject> — <link>" --type review --priority M --company "<company>"`.
Optionally print a suggested `data/jobs/` seed if the role is on a supported ATS (do not create the dir).

## 6. RESULT

Print one line:
`RESULT: {"skill":"inbox-sync","jobs_checked":12,"threads_seen":19,"status_changes":[{"job_id":"..","from":"applied","to":"interview"}],"action_items":3,"push_sent":1,"push":true,"untracked_outreach":1,"pending_file":"data/sync_updates.json"|null,"errors":[]}`
If any interview/offer was found, also include `"ACTION_ITEM":"<company> <class> — <link>"` (first one).
