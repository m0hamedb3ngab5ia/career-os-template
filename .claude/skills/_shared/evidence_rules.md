# Evidence rules (shared by score-job, tailor-resume, write-cover-letter, qa-review)

What counts as profile evidence for a claim. `profile/master.yaml` is the only source; placeholder
bullets (`placeholder: true` or text starting `[FILL IN`) are never evidence.

| Claim type | Acceptable evidence (record this id) | Examples |
|---|---|---|
| **Knows / has used a language or tool** (no number, no outcome) | `profile.skills.<key>` containing the term, OR any non-placeholder entry's `stack` list containing it (`<entry id>.stack`), OR a non-placeholder bullet whose text names it (`<bullet id>`) | "Python", "AWS Glue", "Next.js" in the skills section; "I've worked with Supabase" in a letter |
| **Did something, with a number or an outcome** (a count, %, $, rank, duration, "improved", "reduced", "shipped", "led", "built X that does Y") | a non-placeholder **bullet id** whose text contains that number/outcome verbatim | "2 million events per day" -> `acme.1`; "300 beta users" -> `widgetizer.1` |
| **Motivation / why-this-company** | a `narratives[].id` | `n.data`, `n.builder` |
| **Company / team fact** | `posting.json.description_text` (source `posting`) or a fetched URL | not a profile claim; sourced per write-cover-letter |

Rules:

1. A number never travels without its bullet id. Numbers are frozen: no rounding, combining or
   extrapolating. A claim with a number that cannot cite a bullet id is fabrication. A number written `~N` in a
   bullet with `estimate: true` is the candidate's own estimate: keep the `~` (prose may say "about N");
   never estimate a number yourself (`.claude/skills/_shared/resume_writing_rules.md`, OVERRIDE).
2. `skills.*` / `stack` justify *familiarity only*. They never justify a metric, an outcome, seniority
   ("expert in"), or a duration ("3 years of Go").
3. Synonyms are allowed for the familiarity check only: Postgres/PostgreSQL, JS/JavaScript,
   K8s/Kubernetes, Athena/AWS Athena. Do not stretch: "SQL" is not "PostgreSQL"; "AWS Athena" is not "AWS Lambda".
4. Posting terminology may be mirrored only when evidence exists under these rules; record the pair
   (`term -> evidence id`) in the artifact's `keyword_mirror` / `skill_evidence` map.
5. Evidence id formats: `skills.programming | skills.frameworks | skills.tools | skills.concepts`,
   `<entry id>.stack`, `<bullet id>` (e.g. `acme.3`), `<narrative id>` (e.g. `n.data`).
6. Stronger verbs than the bullet ("led" when the bullet says "supported") are unsupported even
   when the id is cited.
7. Never write anything listed in `profile/confidential_terms.yaml` (`terms`, `patterns`: the current
   employer's internal codenames, hostnames, account-shaped ids), even when a bullet or `context`
   mentions it. Describe the system in plain words instead. `careeros.qa` hard-fails any artifact that does.
