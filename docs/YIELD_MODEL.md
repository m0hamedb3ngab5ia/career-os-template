# Yield model spec

How career-os ranks job-search actions by expected offers per candidate-minute. Priors are fixed config
defaults (`src/careeros/yield_model.py`, override in `config/pipeline.yaml: yield_priors`).

## 1. Objective
Rank every action by expected offers gained per candidate-minute: `score = Δp / c`.
(Greedy on Δp/c is the same ranking as maximizing P(≥1 offer); the product form adds nothing to ranking.)
Outcomes are correlated (same résumé, same market), so any "P(≥1 offer)" shown to the user is an upper bound.

## 2. Offer probability per job (fixed priors in config; no learning in v1)
`p = r_k · o_k · m_fit · m_stale`

| channel k | r_k app→interview | o_k interview→offer | p | grade |
|---|---|---|---|---|
| cold apply | 3% | 6% | 0.18% | B |
| warm referral | 20% (Ashby 40% shrunk for referrer selection) | 10% | 2% | B→C |
| hiring-manager DM (top fit only) | 3% + reply lift, see §4 | 6% | — | C |

- One warm referral ≈ 10 cold applications (range 4–36).
- `m_fit = exp(0.3·(fit−70)/30)` (≈1.35× per 30 points, grade C); referral channel uses m_fit = 1 (referrer already filtered fit).
- `m_stale = 0.7` if posted >60 days or reposted, else 1.0 (C).
- Tailoring is always on, so it is not a lever. Stranger referrals are not an action (Δp ≤ 0).
- Pay bar: parse posted range into the existing `salary_below_min` hard filter; no b_j term.
- Sanity: 21 cold apps → P(≥1 interview) ≈ 47%.

## 3. Cost (candidate minutes; config defaults, grade C)
apply review 2 · referral ask 3 · HM DM 3 · contact refresh 5 · follow-up 1.
Hold back expected interview time `r·300 min` from `minutes_per_week` (≈9 min per cold app, ≈60 per referral)
so good weeks don't overcommit.

## 4. Actions and their Δp
- Referral ask: `Δp = q_ask · s_co · (p_ref − p_cold)`, q_ask 0.4 warm tie / 0.1 weak tie (C).
  `s_co` = company referral strength (weak 0.3 / normal 1 / strong 1.5, default normal), per company and
  per track (new-grad vs experienced) in `companies.yaml`; set from research + the candidate's own reports
  (e.g. a referral program recruiters say barely matters → weak).
- HM DM: `Δp = q_reply · (p_sourced − p_cold)`, q_reply 0.07, p_sourced 1.5% (C).
- Contact refresh: `P(usable) · q_ask · max_j(p_ref,j − p_cold,j)` over that company's open jobs (best one;
  one application per company rule). P(usable) half-life by tie: former colleague/classmate 730 d, met once 180 d.
- All outreach stays draft-only; the user sends. Contacts already connected on LinkedIn stay manual-tailor
  (`outreach.py`). Tier A never submitted.

v1 in practice = a fixed tier order inside `runs/ranking.py`:
1. referral ask at a company with an open job at fit ≥70 and a warm contact;
2. freshest fit-ranked cold applications;
3. contact refreshes when no asks are pending.

## 5. The three modes
- Any position: the ranking above.
- Criteria x,y,z: ranking on a subset + supply report (jobs/week each filter removes), shown as `advise`
  recommendations (suggest-only; `careeros advise apply <id>`). Covers skip insights and flexibility (D4).
- Specific posting: levers by Δp/c: warm referral > HM DM > make yourself sourceable (Open to Work for recruiters,
  headline = target title) > apply fresh.

## 6. Learning (deferred)
Log now, learn later. Success = interview within 45 days; open applications count as censored.
Report per-channel interview rates with Wilson intervals. After ~30 outcomes: one scale factor θ on cold r
(Beta prior strength ~100). Hypotheses (YOE-3 postings, apply ≤48h) run as fixed quotas, e.g. 1 YOE-3 posting/week
at fit ≥80; only 3×+ effects are detectable (2× at 3% needs ~750 apps per arm).

## 7. Goal config
`goal: {pay_bar, minutes_per_week, locations, flex_for_prestige}` in config, set by `careeros goal` (+ chat
equivalent in docs/CHAT.md). Urgent mode deferred until a second user exists.
