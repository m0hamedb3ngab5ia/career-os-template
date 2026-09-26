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
| `scam_<code>` | run `.venv/bin/careeros safety check <job_id>` first (it writes `JOB/safety.json`); one `scam_<code>` per **hard** flag, e.g. `scam_apply_domain`, `scam_free_email_contact`, `scam_phrase`, `scam_registry`. Exit 3 means the command already opened the `scam_suspected` Action Item and set `needs_review`; do not add another. Soft flags (`salary_implausible`, `company_unverified`) go in `reasons` and cost 10 fit points. `scam_lookalike_company` = a name borrowing a known brand on a foreign domain. |

**Ghost-job check** (same `safety.check` run; thresholds in `targets.yaml: safety.ghost`). Before it, when
`data/company_signals.json` has no entry for the company or the entry's `checked_at` is over 30 days old,
WebSearch `"<company>" layoffs OR "hiring freeze" <this year>` and record only what a dated, reputable
source states: `.venv/bin/careeros safety signal "<company>" --kind freeze|layoffs|none --date <YYYY-MM-DD>
--source <url>` (`none` with today's date and the search you ran when nothing is found). Then:
- hard `ghost_stale` (posted 45+ days ago) or `ghost_freeze` (freeze in the last 180 days): the command
  exits 4 and sets status `skipped`; put `ghost_stale` / `ghost_freeze` in `hard_filter_fails`.
- soft `ghost_stale` (30+ days), `ghost_reposted` (same role 3+ times in 90 days), `ghost_unlinked`
  (aggregator posting not found on the company's own site), `ghost_layoffs`: add to `reasons`, 5 fit
  points each; any of them turns auto-submit off for this job.
- dream companies are never skipped: their hard flags come back soft, with a `ghost_job` Action Item.

**Made-up company check** (only when `safety.json` has `company_unverified`: the company is on none of
your boards, dream list, prestige tiers or `company_domains`). Verify with WebSearch/WebFetch, recording
only what a source shows:
1. An official website exists on a normal domain and its own careers page (or its ATS board) lists this role.
2. A LinkedIn company page with real employees (dozens or more), or news / funding / SEC coverage.
3. The site is not brand new or a template shell, and the recruiter's email domain matches the website.

All hold → `.venv/bin/careeros safety verify "<company>" --domain <domain> --evidence "<urls, sizes>"`,
then rerun `careeros safety check <job_id>`. Any fails, or nothing found → `careeros safety flag
"<company>" --domain <domain> --reason "could not verify company"` and `scam_company_unverified` in
`hard_filter_fails`. Tier A never applies here (dream companies are curated).
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
  "scored_at": "<ISO8601 UTC>"
}
```
(`reasons` and `prestige` duplicate `fit_reasons`/`prestige_tier` for the tracker's Score model.)

Append to `JOB/log.md`: `- YYYY-MM-DD HH:MM:SS [score-job] category=<c> fit=<n> tier=<t> decision=<d> <skip_reason?>`
(format `- YYYY-MM-DD HH:MM:SS [<skill>] <message>`, local time, identical to `store.append_log`; e.g. `date '+%F %T'`).

## 9. Print the summary line (last line of output, single line)

`RESULT: {"skill":"score-job","job_id":"...","category":"...","fit":78,"tier":"C","decision":"prepare","skip_reason":null,"hard_filter_fails":[],"profile_gap":null}`
