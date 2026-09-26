---
name: score-job
description: Score and categorize one job posting (data/jobs/<id>/posting.json) against config/*.yaml and profile/master.yaml. Writes score.json with category, fit 0-100, tier A/B/C, hard-filter fails and prepare/skip decision. Use before any tailoring.
---

# score-job

`$ARGUMENTS` = path to a job dir, e.g. `data/jobs/a1b2c3d4e5f6`. Call it `JOB`.

You are a deterministic-as-possible classifier. Do not browse the web. Do not invent skills the
profile does not have. Every number you write must follow the rubric below so that two runs on the
same posting give the same score (+/- 3).

## 1. Read inputs

1. `JOB/posting.json` (fields: job_id, company, title, location, url, apply_url, ats,
   description_text, salary_min, salary_max, departments).
2. `config/categories.yaml` (categories, `title_keywords`, `skill_keywords`, `excluded`).
3. `config/targets.yaml` (candidate, location, categories, industries, thresholds, tiers, tier_rules).
4. `config/companies.yaml` (dream_list, blocklist, already_applied, prestige_tiers, prestige_scoring).
5. `profile/master.yaml` (skills.*, experience[].stack, projects[].stack, bullets, education).
   Ignore bullets with `placeholder: true` or text starting `[FILL IN` when judging evidence.

If `posting.json` is missing or has no `description_text`, write nothing and print
`RESULT: {"job_id": "<dir name>", "error": "posting.json missing or empty"}` and stop.
If `posting.json` has `pruned: true` (retention cut the description to a preview), write nothing and print
`RESULT: {"job_id": "<dir name>", "error": "posting pruned by retention"}` and stop.

## 2. Hard filters (any hit => decision `skip`)

Add one string per hit to `hard_filter_fails`, wording exactly:

| fail string | rule |
|---|---|
| `sponsorship_required` | posting says sponsorship is unavailable AND candidate `needs_sponsorship: true` (currently false, so only flag if the posting REQUIRES a non-US work status, e.g. "must hold EU work permit"). Do not flag "we do not sponsor" for a US citizen. |
| `clearance_required` | mentions active/required security clearance, TS/SCI, "must be able to obtain a clearance" |
| `location_blocked` | job country in `location.blocked_countries`, or on-site in a country not in `allowed_countries` (`"*"` = any) |
| `industry_blocked` | industry (see step 4) in `industries.blocked` or `companies.blocklist.industries` |
| `company_blocked` | company matches `blocklist.companies` or any `blocklist.name_patterns` substring (case-insensitive) |
| `yoe_gt_3` | minimum required years of professional experience explicitly > 3 (e.g. "5+ years"). Internship-only requirements never trigger this. |
| `title_excluded` | category resolves to one with `excluded: true` |
| `salary_below_min` | `salary_max` is a number and `< candidate.min_base_usd`. Unknown salary = allowed. |
| `already_applied_recent` | (company, role family) in `companies.already_applied` with date < 90 days ago |
| `safety_block` / `safety_skip` | the safety verdict (below) is `block` or `skip` |

**Safety verdict** (run before fit): `.venv/bin/careeros safety check <job_id>` writes `JOB/safety.json`
with `verdict` = **Pass** / **Review** / **Block** (or `skip` for a dead posting) and every flag's reason
code, level, evidence URLs and timestamp. Levels are configurable per code in `targets.yaml: safety.levels`.
- **Block** (exit 3; the CLI already opened the `scam_suspected` Action Item, set `needs_review` and
  recorded the company): payment / gift cards / crypto / check deposits / buying equipment
  (`SCAM_PAYMENT_REQUEST`), remote-access software (`SCAM_REMOTE_ACCESS_REQUEST`), brand impersonation
  (`SCAM_BRAND_DOMAIN_MISMATCH`), contradictions (`COMPANY_CONTRADICTIONS`), a high-confidence registry
  entry (`SCAM_FLAGGED_BEFORE`). Add `safety_block` to `hard_filter_fails`; do not add another item.
- **Skip** (exit 4, status `skipped`): `GHOST_STALE_NO_ACTIVITY` = very old AND not updated recently AND
  the company posts nothing new AND not an evergreen / senior role. Add `safety_skip`.
- **Review**: score normally, but auto-submit is off (`safety.json: auto_submit_allowed: false`); the job
  goes to assisted mode for human approval. Codes: `SCAM_APPLY_DOMAIN_UNRECOGNIZED`,
  `SCAM_FREE_EMAIL_RECRUITER`, `SCAM_CHAT_ONLY_INTERVIEW`, `SCAM_NO_INTERVIEW`, `SCAM_SALARY_IMPLAUSIBLE`,
  `COMPANY_NOT_YET_CHECKED`, `COMPANY_SPARSE_PUBLIC_FOOTPRINT`, `GHOST_OLD_POST` (45+ days with activity),
  `GHOST_REPOSTED`, `GHOST_AGGREGATOR_ONLY`, `GHOST_HIRING_FREEZE` (only when the freeze covers the role).
  List them in `reasons`, 5 fit points each.
- **info** only lowers confidence: `GHOST_OLD_POST` (30+ days), `GHOST_RECENT_LAYOFFS`, a freeze that does
  not cover the role. 3 fit points each; never changes the decision.
- Company priority changes the review threshold, never a fraud judgment: a dream company is never skipped
  (skip becomes review, with a `ghost_job` Action Item), but its Block flags still block.

**Hiring signals.** When `data/company_signals.json` has no entry for the company or `checked_at` is over
30 days old, WebSearch `"<company>" layoffs OR "hiring freeze" <this year>` and record only what a dated,
reputable source states, including what the freeze covers:
`.venv/bin/careeros safety signal "<company>" --kind freeze|layoffs|none --date <YYYY-MM-DD> --scope
"<company-wide | teams; locations>" --source <url>` (`none` with today's date when nothing current is
found, or when a freeze was lifted). Then rerun `safety check`.

**Company check** (when `safety.json` has `COMPANY_NOT_YET_CHECKED`). Do not reject a company because it
is unfamiliar, small, new, or missing from known lists. Sparse information alone is not evidence of fraud.
Gather independent signals with WebSearch/WebFetch, then record the risk level:

- **Low** (normal scoring and auto-submit) when several hold: the role is on the company's careers page
  or a reputable ATS / LinkedIn Jobs; a working official website that clearly describes the business; a
  consistent LinkedIn presence with identifiable employees or founders; company domain, recruiter email,
  posting and application URL agree; external references (Crunchbase, press, GitHub, accelerator,
  customers, incorporation history).
  `.venv/bin/careeros safety verify "<company>" --risk low --domain <domain> --signal "<signal 1>" --signal "<signal 2>" --evidence <url> ...` (two signals minimum).
- **Medium** (score it, human approves before submit): very new or little public history; tiny or
  founders-only team; role only on LinkedIn or an ATS, not the company site; minimal but consistent
  website; a third-party recruiting firm; sparse information but no direct scam signal.
  `... --risk medium --signal "<what was found>" --evidence <url>`.
- **High** (block, explain exact red flags): the application domain impersonates or closely resembles
  another company; a recruiter claims a company but uses an unrelated personal or suspicious domain with no
  verifiable recruiting relationship; payment, gift cards, crypto, vendor equipment purchases, banking
  credentials or SSN before legitimate onboarding; company name, website, recruiter and listing materially
  contradict each other; the role cannot be found through any independent source and the company does not
  appear connected to it; a domain recently created to impersonate a known company; chat-only interviews
  with no verifiable company representative.
  `... --risk high --signal "<each red flag>" --evidence <url>`.

Use accumulated evidence, never one missing signal. Then rerun `safety check`.
| `prestige_avoid` | company in `prestige_tiers.avoid`: skip, unless the fit **before** `prestige_bonus` (sum of the other components, section 5) is >= 90, then flag `needs_review_avoid` instead |

## 3. Category

Score every category in `categories.yaml`:
- title match: +3 per `title_keywords` phrase found in `title` (case-insensitive, whole phrase), +1 if found only in `description_text`.
- skill match: +1 per `skill_keywords` term found in `description_text`.
Pick the highest; ties -> the one listed first in `targets.categories.primary`, then `secondary`.
`category_confidence` = winner_score / (winner_score + runner_up_score), rounded to 2 decimals (1.0 if runner-up 0).
Excluded categories compete too (so a PM posting is labeled `product_manager` and skipped).
If no category scores > 0: category `unknown`, confidence 0, decision `skip`, skip_reason `no_category_match`.

## 4. Extract from the posting

- `required_skills[]`: concrete technologies/skills the posting asks for (languages, frameworks,
  clouds, databases, tools, methods like "distributed systems", "ETL"). Normalize casing
  (`Python`, `PostgreSQL`, `AWS`, `Kafka`, `CI/CD`). Deduplicate. Requirements listed under
  "required"/"what we look for"/"you have" count; "nice to have" goes in `nice_to_have_skills[]`.
- `matched_skills[]`: subset of required_skills with evidence in the profile per
  `.claude/skills/_shared/evidence_rules.md` (familiarity: `skills.*`, any `stack`, or a
  non-placeholder bullet text; allowed synonyms listed there). Record the evidence id in
  `skill_evidence` map `{skill: "skills.programming" | "<bullet id>" | "<entry id>.stack"}`.
- `missing_skills[]` = required minus matched. NEVER move a skill to matched without an evidence id.
- `industry`: one of `ai_ml, hedge_fund, quant_trading, fintech, developer_tools, infra_cloud,
  consumer, enterprise_saas, healthcare, defense, gambling, adult, mlm, other` from the company
  description and `departments`.
- `seniority_guess`: `new_grad | early_career | mid | senior | staff+` from title words (New Grad,
  Early Career, I/II, Senior, Staff, Principal, Lead) and stated YOE.
- `salary_est`: `{min, max, source}` where source = `posting` if numbers present, else your estimate
  from title+location+industry with source `estimate` (be conservative; new-grad NYC backend
  110k-160k). Never present an estimate as posted.
- `prestige_tier`: the key in `prestige_tiers` whose list contains the company (case-insensitive,
  normalize "Inc", "Securities" variants only if the list uses them), else `null`.

## 5. Fit score (0-100), exact rubric

| component | max | how |
|---|---|---|
| skills_overlap | 40 | `40 * len(matched)/len(required)`; if required is empty use 24 (neutral). Round to int. |
| experience_relevance | 30 | Count non-placeholder profile entries (experience + projects) whose `tags` include the category, or whose stack overlaps >= 2 required skills. 0 -> 5, 1 -> 15, 2 -> 22, 3+ -> 30. Subtract 5 if the strongest matching entry is a course project only. |
| seniority_match | 15 | new_grad or early_career -> 15; mid (2-3 yrs) -> 8; senior+ -> 0 |
| location_pref | 10 | in `location.preferred` or remote_ok remote -> 10; `preferred_regions` -> 7; elsewhere in US -> 4; allowed non-US -> 2 |
| industry_boost | 5 | industry in `targets.industries.boost` -> 5 else 0 |
| prestige_bonus | +/- | `prestige_scoring.bonus[prestige_tier]` (0 if null) |

`fit = min(100, max(0, sum))`. Put each component's value in `fit_breakdown` and one sentence per
component in `fit_reasons[]` (e.g. "skills 7/10 matched: missing Go, Kafka, Terraform").

## 6. Tier

Build `dream = companies.dream_list + every company in prestige_tiers[t] for t in prestige_scoring.auto_dream`.
Apply `targets.tier_rules` in order, first match wins:
- `company_in dream_list` -> A
- `fit >= 85` -> B
- `fit >= 70` -> C
- else `null`.

## 7. Decision

```
if hard_filter_fails:                 decision=skip, skip_reason=first fail
elif category excluded/unknown:       decision=skip
elif tier == "A" and fit >= thresholds.tier_a_min_fit:  decision=prepare  (flag "tier_a_low_fit" in fit_reasons if fit < min_fit_to_prepare)
elif location not preferred and fit < thresholds.min_fit_nonpreferred_location: decision=skip, skip_reason=location_nonpreferred_low_fit
elif fit >= thresholds.min_fit_to_prepare: decision=prepare
else: decision=skip, skip_reason=below_min_fit
```

**Company gate** (only when the decision above is `prepare`). Caps per company, the rejection cooldown
and posting close dates are code (`src/careeros/company_policy.py`), not judgment:
1. Write `JOB/score.json` (section 8) with `decision: "prepare"` first, so the gate sees this job's fit and category.
2. Run `.venv/bin/careeros company gate <job_id> --json`.
   - Exit 0: keep `prepare`. Copy `urgent`, `closes_at` and `action_note` into `score.json` as `company_gate`.
   - Exit 3: `decision=skip`, `skip_reason` = the gate's `reason`: `company_cap` (the company's slots are
     used: `volume.max_per_company_per_90_days` or its `company_caps` entry; higher-fit similar roles
     hold the rest), `cooldown` (rejected there within `volume.same_company_cooldown_days` and this
     posting does not close before the cooldown ends), or `not_similar` / `closed` / `unscored`. Put the
     gate's `detail` in `fit_reasons`, then rewrite `score.json`.
   `company_cap` and `cooldown` are deferrals, not verdicts: `careeros company requeue` re-checks every
   job skipped for them (a slot frees up, the cooldown ends) and sets the open ones back to `scored` for
   another /prepare-job. Never skip a job as `company_cap` / `cooldown` without the gate saying so.

`profile_gap` (string or null): set it when either holds, naming the entry:
- the category's `bullet_priority[0]` entry has no non-placeholder bullets (`placeholder: true` or text
  starting `[FILL IN`) -> `"<entry_id> bullets are placeholders; tailoring will use next entries"`;
- any entry in `bullet_priority` has only `placeholder_partial: true` bullets (no fully usable bullet)
  -> `"<entry_id> has only placeholder_partial bullets; tailoring will skip it"`.
If both apply, join the messages with `; `. Entries that mix usable and partial bullets are not a gap.

## 8. Write `JOB/score.json`

```json
{
  "job_id": "...", "company": "...", "title": "...",
  "category": "swe_backend", "category_confidence": 0.86,
  "fit": 78, "fit_breakdown": {"skills_overlap": 28, "experience_relevance": 22, "seniority_match": 15, "location_pref": 10, "industry_boost": 5, "prestige_bonus": 0},
  "fit_reasons": ["..."], "reasons": ["...same list..."],
  "hard_filter_fails": [],
  "required_skills": [], "nice_to_have_skills": [], "matched_skills": [], "missing_skills": [], "skill_evidence": {},
  "prestige_tier": null, "prestige": null, "industry": "fintech", "seniority_guess": "new_grad",
  "tier": "C", "decision": "prepare", "skip_reason": null,
  "salary_est": {"min": 135000, "max": 165000, "source": "posting"},
  "salary_ok": true, "location_ok": true, "profile_gap": null,
  "company_gate": {"urgent": false, "closes_at": null, "action_note": ""},
  "scored_at": "<ISO8601 UTC>"
}
```
(`reasons` and `prestige` duplicate `fit_reasons`/`prestige_tier` for the tracker's Score model.)

Append to `JOB/log.md`: `- YYYY-MM-DD HH:MM:SS [score-job] category=<c> fit=<n> tier=<t> decision=<d> <skip_reason?>`
(format `- YYYY-MM-DD HH:MM:SS [<skill>] <message>`, local time, identical to `store.append_log`; e.g. `date '+%F %T'`).

## 9. Print the summary line (last line of output, single line)

`RESULT: {"skill":"score-job","job_id":"...","category":"...","fit":78,"tier":"C","decision":"prepare","skip_reason":null,"hard_filter_fails":[],"profile_gap":null,"urgent":false,"closes_at":null}`
