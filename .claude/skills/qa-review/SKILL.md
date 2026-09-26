---
name: qa-review
description: Critic gate for a prepared job dir. Runs deterministic checks (python -m careeros.qa), then scores relevance, specificity, voice_match, zero_fabrication and ats_safety 1-10 with a full fabrication audit. Writes qa.json with pass/fail, fail_reasons and regenerate_suggestions.
---

# qa-review

`$ARGUMENTS` = job dir (`JOB`). You are the adversarial reviewer. Your job is to find every claim that
is not backed by `profile/master.yaml` and every rule in `config/qa.yaml` that was broken. Be strict;
a pass here means the artifacts may be submitted without a human reading them (tier B/C).

## 1. Read

- `config/qa.yaml` (rubric list, `pass_threshold`, `max_regenerations`, banned phrases, style rules,
  per-artifact hard/soft rules).
- `profile/master.yaml` and `profile/voice/style_guide.md` (+ `samples/`).
- `.claude/skills/_shared/resume_writing_rules.md` (bullet formulas, weak openers, ownership honesty; the
  `bullet_strength` rubric row below scores against it).
- `JOB/posting.json`, `JOB/score.json`, and whichever exist of `resume.json`, `resume.txt`,
  `cover_letter.md`, `answers.json`, `resume.pdf`, `outreach.json`, `contacts.json`.
- `JOB/qa.json` if it exists: read `regenerations` (default 0).

## 2. Deterministic checks

Run `.venv/bin/python -m careeros.qa JOB`. Parse the JSON: `pass`, `checks[]` ({check, level, ok, detail, skipped?}),
`fail_reasons[]`, `warnings[]`, `keyword_coverage`, `cover_letter_word_count`, `orphan_numbers[]`,
`unknown_tools[]`, `banned_hits[]`, `bullet_shape[]` ({id, line, issues}: soft `weak_opener` / `no_metric` / `too_long`
warnings, never a fail; the hard `estimate_marked` check fails a candidate estimate shown without its `~`),
`confidential_hits[]` (terms/patterns from `profile/confidential_terms.yaml`
found in resume.txt, cover_letter.md, answers.json or outreach.json; always a hard fail, never waived).

Extended checks (same `checks[]` records; their details in four extra keys):
- `wrong_company_hits[]` ({file, name, context}): hard `wrong_company`, another company's name (companies.yaml,
  other job dirs' postings) left in the letter, a generated answer or an outreach draft. The hard
  `cover_letter_names_company` accepts this company's aliases (`qa.yaml consistency.company_aliases`) and domain stems.
- `consistency` ({docs, letter_off_resume, title_mismatches, title_uncertain, number_mismatches, number_paraphrases}):
  hard `employer_title_consistent` (title/degree/year for an employer or school differs from the résumé header) and
  `numbers_consistent` (a restated bullet number differs: "3 million" vs "2 million"); soft
  `letter_experiences_on_resume`, `employer_title_uncertain`, `numbers_paraphrased`.
- `outreach_policy` ({present, drafts, manual_contacts, violations[{check, contact, issue}], word_counts}): hard
  `outreach_manual_contacts`, `linkedin_draft_only`, `linkedin_note_length` (> 300 chars; LinkedIn truncates),
  `email_autosend_verified`, `thank_you_manual`, `outreach_cold_limit`, `outreach_json_valid`; soft
  `outreach_word_counts`. All skipped when there is no outreach.json.
- `pdf_fidelity` ({text_recall, missing_tokens, split_tokens, extra_tokens, links_found, links_missing,
  fonts_not_embedded, metadata, file_name} or {skipped}): hard `pdf_links_clickable`, `pdf_text_matches_resume`
  (soft between `text_recall_soft` and `text_recall_hard`); soft `pdf_text_split_words`, `pdf_hidden_text`,
  `pdf_fonts_embedded`, `pdf_metadata`.

Store the whole object as `deterministic`. If the command itself errors, set
`deterministic = {"pass": false, "error": "<stderr>"}` and treat as a hard fail.

## 3. Fabrication audit (do this before scoring)

For `cover_letter.md` body, every generated answer in `answers.json` and every `outreach.json` draft text
(`linkedin_note`, `linkedin_message`, `email.subject`/`email.body`, `followup_7d`, `followup_14d`, and each
`followups[]` item; artifact `outreach.json#<i>.<field>`), split into sentences. For each
sentence that asserts something about the candidate (an action, a result, a tool, a number, a motivation),
create an entry:

```json
{"artifact": "cover_letter.md", "claim": "<sentence or clause>", "support": "<bullet/narrative id>" | "UNSUPPORTED", "note": "<why, e.g. number 3 million not in acme.1 (2 million)>"}
```
Rules: apply `.claude/skills/_shared/evidence_rules.md`. A claim of merely knowing/using a tool is
supported by `profile.skills.<key>` or any entry `stack` (support id `skills.<key>` / `<entry>.stack`).
A claim with a number or outcome needs a bullet id listed in that artifact's frontmatter/entry (for outreach, the
draft's `bullet_ids` / `narrative_ids`) AND the
bullet text must contain the substance (same number, same tool, same outcome). Paraphrase is fine; a
changed number, an added tool, or a stronger outcome ("led" when bullet says "supported") is UNSUPPORTED.
Company facts are checked against `facts_used` and the posting text; an unsourced company fact is
UNSUPPORTED. Sentences with no factual claim (greeting, the ask) get support `n/a`.

Also audit `resume.txt` bullets against their `resume.json` ids: any bullet whose text adds a number,
tool, or outcome not in the profile bullet -> UNSUPPORTED entry with artifact `resume.txt`.

`unsupported_count` = number of UNSUPPORTED entries.

## 4. Rubric (1-10 each, integer, one-line justification)

| key | 10 means | automatic caps |
|---|---|---|
| relevance | resume top bullets and letter main experience hit the posting's top 2 requirements; category-appropriate ordering | cap 5 if `keyword_coverage` < 0.4; cap 7 if the letter never names the team's actual work |
| specificity | every paragraph has a concrete number/system/name; facts are checkable | cap 6 if `facts_used` < 2 or any fact is generic ("innovative company") |
| voice_match | reads like `style_guide.md` (its register and structure, first person, plain ask, no praise) and the density of any `voice/examples/` letter; matches `## Learned` patterns where the guide does not override them | cap 6 if em-dashes > 2, rhetorical question, tricolon of adjectives, or any throat-clearing opener; cap 7 if the letter restates the résumé instead of 1-2 chosen experiences, or lists tools as a comma chain; cap 8 if `voice_verified: false` (cannot verify beyond rules) |
| zero_fabrication | `unsupported_count == 0` and deterministic truth_trace/number_audit/tool_audit ok | 1 if any number/tool fabricated; max 4 if any UNSUPPORTED; 10 only when zero |
| ats_safety | single column, standard section headers, contact intact, no tables/icons, keyword coverage >= 0.6, 1 page, clickable links, PDF text = resume.txt | cap 5 if `contact_intact`, `pdf_page_count`, `pdf_links_clickable` or `pdf_text_matches_resume` hard-failed; cap 7 if coverage < 0.6 or `pdf_text_split_words` is reported |
| bullet_strength | resume.txt bullets follow `resume_writing_rules.md`: action verb first, technical what, impact/scale, tech named; team work worded "contributed to" / "member of" | cap 7 if `bullet_shape` has any `weak_opener`; cap 8 if more than a third of bullets are `no_metric` |

`mean` = average of the five keys in `critic.model_rubric` (relevance .. ats_safety), 2 decimals.
`bullet_strength` is advisory: it is scored and written to `rubric`, but it is not in `mean` and never a
fail reason (bullets are frozen profile text; regenerating cannot add a number). When it is below 7, its
`why` names the weakest bullet ids and one metric question per bullet without a number (never a guessed
value; `resume_writing_rules.md` OVERRIDE).

## 5. Decide

```
hard_ok  = deterministic.pass
rubric_ok = mean >= critic.pass_threshold (7.5) and zero_fabrication >= 8
pass = hard_ok and rubric_ok
```
`fail_reasons[]`: every deterministic hard fail (verbatim `fail_reasons`), every UNSUPPORTED claim
(`"fabrication: <claim> (<artifact>)"`), every `critic.model_rubric` key below 7 (`"<key>=<n>: <justification>"`; never `bullet_strength`), and,
when `mean < pass_threshold` or `zero_fabrication < 8` even though no key is below 7,
`"critic_mean=<mean> < <threshold>"` (or `"zero_fabrication=<n> < 8"`), so a failed rubric always has a reason.

`regenerate_suggestions[]`: one actionable instruction per fail reason (for a `critic_mean` reason: one each
for the two lowest-scoring keys, naming what would raise them), addressed to the writer skill,
e.g. `{"skill":"write-cover-letter","suggestion":"Replace 'millions of events' with the exact 2 million from acme.1"}`,
`{"skill":"tailor-resume","suggestion":"Remove 'Docker' from skills (not in profile); add initech_intern.1 to cover ETL"}`.
Route the extended checks by the file named in the failure:
- `wrong_company`, `employer_title_consistent`, `numbers_consistent` (and a failed `cover_letter_names_company`):
  `write-cover-letter` for cover_letter.md, `answer-question` for answers.json, `draft-outreach` for outreach.json
  (name the leftover company / the résumé's title or number to use).
- `outreach_*`, `linkedin_draft_only`, `linkedin_note_length`, `email_autosend_verified`, `thank_you_manual`:
  `draft-outreach` (e.g. "shorten Jane Doe's linkedin_note to <= 300 chars", "set send_after null for the manual contact").
- `pdf_links_clickable`, `pdf_text_matches_resume`, `pdf_text_split_words`, `pdf_hidden_text`, `pdf_fonts_embedded`,
  `pdf_metadata`: `tailor-resume` (re-render `templates/resume/render.py`); when the fault is in the template itself
  (metadata, fonts, kerning splits on a fresh render) say so: `{"skill":"tailor-resume","suggestion":"template:
  templates/resume/<name>.tex <fix>"}`.
Missing artifacts that the tier requires (resume always; cover letter when tier rule says `always`) are
a fail with suggestion `{"skill":"<writer>","suggestion":"artifact missing"}`.

## 6. Write `JOB/qa.json`

```json
{
  "job_id": "...", "reviewed_at": "<ISO>",
  "deterministic": { ...full output of careeros.qa... },
  "rubric": {
    "relevance": {"score": 8, "why": "..."}, "specificity": {"score": 7, "why": "..."},
    "voice_match": {"score": 7, "why": "..."}, "zero_fabrication": {"score": 10, "why": "..."},
    "ats_safety": {"score": 9, "why": "..."}, "bullet_strength": {"score": 7, "why": "..."}
  },
  "fabrication_audit": [ ... ], "unsupported_count": 0,
  "mean": 8.2, "pass": true,
  "fail_reasons": [], "regenerate_suggestions": [],
  "regenerations": <count so far, unchanged by this skill>,
  "max_regenerations": 1,
  "next_action": "queue" | "regenerate" | "action_item"
}
```
`next_action`: `queue` if pass; `regenerate` if fail and `regenerations < max_regenerations`;
`action_item` if fail and regenerations already >= max.

Append to `JOB/log.md`: `- YYYY-MM-DD HH:MM:SS [qa-review] pass=<b> mean=<x> hard_fails=<n> unsupported=<n> next=<next_action>`
(format `- YYYY-MM-DD HH:MM:SS [<skill>] <message>`, local time, identical to `store.append_log`; e.g. `date '+%F %T'`).

## 7. RESULT

`RESULT: {"skill":"qa-review","job_id":"...","pass":true,"mean":8.2,"hard_fails":0,"unsupported":0,"next_action":"queue","regenerate":[],"fail_reasons":[]}`

- When `next_action == "regenerate"`: the caller must increment `regenerations` in qa.json, rerun each
  skill named in `regenerate` (`.claude/skills/<skill>/SKILL.md`) passing `--suggestions "<joined suggestions>"`,
  then run qa-review again.
- When `next_action == "action_item"`: add `"ACTION_ITEM":"qa_failed_twice: <top 2 fail reasons>"` to
  RESULT. The caller creates it with `careeros action add "<text>" --type qa_fail --job <job_id> --priority H`
  and sets status `needs_review`.
