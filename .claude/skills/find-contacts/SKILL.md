---
name: find-contacts
description: For a job dir, identify the likely recruiter, hiring manager and team lead from the posting text and the company site (WebFetch), build LinkedIn people-search URLs (never automated LinkedIn browsing), and guess email patterns with confidence levels. Writes contacts.json. Never sends anything.
---

# find-contacts

`$ARGUMENTS` = job dir (`JOB`). Output: `JOB/contacts.json`. This skill never messages anyone and
never logs into or scrapes LinkedIn. It only reads public pages and constructs search URLs.

## 1. Read

`JOB/posting.json` (company, title, departments, url, description_text), `JOB/score.json` (tier,
category). Read `config/targets.yaml` tiers: if tier C (`outreach: never`) stop with
`RESULT: {"skill":"find-contacts","job_id":"...","skipped":"tier_c_no_outreach"}`.

## 2. Sources, in order (stop adding when you have >= 3 contacts or all sources are exhausted)

1. Posting text: names and titles mentioned ("reports to", "you'll work with", recruiter signature,
   "contact <name>"), team name(s). Source `posting`, confidence `high` for names literally present.
2. Company site via WebFetch (load the tool with ToolSearch if deferred; max 4 fetches):
   - homepage -> find `/team`, `/about`, `/company`, `/leadership`, `/engineering`, `/blog`.
   - Extract people whose titles match: recruiter / talent / people ops (role `recruiter`);
     engineering manager / head of / director of the posting's department (role `hiring_manager`);
     staff/lead engineer on that team (role `team_lead`). Source = page URL, confidence `high`.
   - Engineering blog authors on posts about the team's systems -> role `team_lead`, confidence `medium`.
   If WebFetch is unavailable, skip and note `"web": false`.
3. LinkedIn search URLs (always produce these; they are for the candidate to open manually):
   - recruiter: `https://www.linkedin.com/search/results/people/?keywords=<Company> recruiter <department>`
   - hiring manager: `https://www.linkedin.com/search/results/people/?keywords=<Company> engineering manager <team>`
   - team lead: `https://www.linkedin.com/search/results/people/?keywords=<Company> <team> engineer`
   - university overlap: `https://www.linkedin.com/search/results/people/?keywords=<Company> <profile education[0].school>`
   URL-encode spaces as `%20`. These are `search_urls`, not contacts.
4. Email pattern guess. Determine the company domain (from the posting URL if it is the company's own
   domain, else the homepage from step 2, else `<company-lowercase-no-spaces>.com` with confidence `low`).
   For each named contact produce candidates `first.last@domain`, `first@domain`, `flast@domain`.
   `email_confidence`: `verified` only if the exact address appeared on a public page (cite it);
   `medium` if the domain's pattern was observed for another employee on a public page; else `low`.
   Never mark verified without a URL.

LinkedIn relationship: this skill never opens LinkedIn, so it cannot see whether the candidate is already
connected to someone. Leave `linkedin_degree` and `mutuals` null. The candidate records what their own logged-in
LinkedIn shows when they open the search URLs: `careeros outreach mark <job_id> "<name>" --degree 1` (connected)
or `--mutuals <n>`. `draft-outreach` reads these (see its step 1).

Referral: if any found person lists one of the candidate's schools (`profile/master.yaml: education[].school`)
or past employers (`experience[].company`) in a public bio, set `possible_referral: true` and explain in `note`.

## 3. Write `JOB/contacts.json`

```json
{
  "job_id": "...", "company": "...", "domain": "ledgerline.com", "domain_confidence": "high|medium|low",
  "found_at": "<ISO>", "web": true,
  "contacts": [
    {"name": "Jane Doe", "title": "Technical Recruiter", "role": "recruiter|hiring_manager|team_lead|other",
     "linkedin": "https://www.linkedin.com/in/... or null", "source": "posting|<url>", "confidence": "high|medium|low",
     "email_candidates": ["jane.doe@ledgerline.com", "jane@ledgerline.com"], "email": null,
     "email_confidence": "verified|medium|low", "possible_referral": false,
     "linkedin_degree": null, "mutuals": null, "note": ""}
  ],
  "search_urls": {"recruiter": "...", "hiring_manager": "...", "team_lead": "...", "alumni": "..."},
  "team": "Payments Platform",
  "gaps": ["no names in posting", "team page has no engineering leads"]
}
```
`email` stays null unless `email_confidence` is `verified`. The caller (tracker) copies contacts into
the Contacts tab; `draft-outreach` reads this file next.

Append to `JOB/log.md`: `- YYYY-MM-DD HH:MM:SS [find-contacts] <n> contacts (<roles>), web=<b>, domain=<d> (<conf>)`
(format `- YYYY-MM-DD HH:MM:SS [<skill>] <message>`, local time, identical to `store.append_log`; e.g. `date '+%F %T'`).

## 4. RESULT

`RESULT: {"skill":"find-contacts","job_id":"...","contacts":2,"roles":["recruiter","hiring_manager"],"verified_emails":0,"web":true,"search_urls":4,"gaps":["..."]}`
If `contacts` is 0: add `"ACTION_ITEM":"find-contacts: no names found for <company>; open search_urls in contacts.json"`.
