# Résumé writing rules (shared by tailor-resume, qa-review, and anyone editing profile bullets)

How a good career-os résumé bullet reads, and how to choose between the bullets and variants that
`profile/master.yaml` already holds. Adapted from the vendored ResumeSkills frameworks (MIT, reference
only, never loaded as skills):
`third_party/resumeskills/resume-bullet-writer/SKILL.md`,
`third_party/resumeskills/tech-resume-optimizer/SKILL.md`,
`third_party/resumeskills/resume-quantifier/SKILL.md`,
`third_party/resumeskills/resume-tailor/SKILL.md`,
`third_party/resumeskills/resume-ats-optimizer/SKILL.md`.

These rules sit under `.claude/skills/_shared/evidence_rules.md` and the anti-fabrication contract of
`tailor-resume`: when a rule here and one there disagree, evidence_rules.md wins. Where they disagree with the
vendored files, this file wins.

## OVERRIDE: never estimate or invent a number

**This replaces every estimation technique in the vendored files** ("conservative estimates", "estimate
low", ranges like "8-12", "X+" floors, "if you think it was 60%, say 50%", percentages of a total the
candidate never stated, "find related metrics"). None of that applies in career-os.

1. **Never estimate or invent a number.** Not in a résumé, not in `profile/master.yaml`, not as a range, a
   floor ("100+"), a rounded figure, or a "~" figure you made up. A number exists only when the candidate
   wrote it into a bullet's `text` (and `metrics`). evidence_rules.md rule 1 still holds: numbers are frozen.
2. **A bullet without a metric gets a question, not a number.** Add one entry to the top-level
   `metric_questions` list of `profile/master.yaml` for the candidate to answer:
   ```yaml
   metric_questions:
     - bullet_id: acme.3
       question: How long did a deploy of those three services take before and after Docker (minutes)?
   ```
   One concrete, answerable question per bullet (a count, a before/after, a frequency, a user or request
   volume), no leading suggestion of a value. Skip it if an open question for that `bullet_id` exists.
   Pipeline skills (tailor-resume, qa-review) never edit `profile/master.yaml`: they propose the question
   (tailor-resume in `resume.json` `meta.metric_questions`, which prepare-job turns into a `metric_question`
   Action Item; qa-review in the `bullet_strength` `why`) and the candidate, or an interactive
   profile-editing session with the candidate, adds it. `careeros doctor` WARNs
   "N metric questions open in profile/master.yaml" until the list is empty.
3. **Candidate-supplied estimates are marked.** If the candidate answers with an estimate of their own ("about
   40%"), the bullet text carries a `~` prefix on that number (`~40%`) and the bullet gets `estimate: true`.
   The `~` and the flag are never added or dropped by a skill; the number is still frozen. When the candidate
   answers, they edit the bullet's `text` and `metrics` and delete the question.
4. **"Every bullet has a number" is a soft target, not a rule.** A true bullet without a number beats a
   fabricated one. QA's `bullet_shape` check only warns; a missing metric never fails a résumé and never
   justifies rewriting a bullet.

## Formulas

Use these when writing or reviewing bullets in `profile/master.yaml` (the only place bullet text is
written). tailor-resume never writes new text: it picks the bullet `text` or declared `variants` that fit
these shapes best.

- **X-Y-Z** (Google): "Accomplished **X** as measured by **Y** by doing **Z**". X = the outcome, Y = the
  number that proves it, Z = what the candidate did. Example: "Cut manual report prep by 5 hours per week by
  writing 12 Airflow DAGs in Python that move SQL reports into a warehouse".
- **Tech bullet formula:** **[action verb] + [technical what] + [scale/impact] + [technology]**. Example:
  "Built a FastAPI service in Python that ingests Kafka order events into PostgreSQL, processing 2 million
  events per day".
- **Condensed STAR / CAR:** one sentence that keeps the Challenge (or Situation/Task), the Action and the
  Result, dropping the setup prose. Example: "Profiled data quality and documented lineage across 30 SQL
  tables with Python checks, giving the reporting team one traced source per field".

## Power verbs

Start every bullet with a past-tense verb (present tense for a current role is fine if the whole entry
uses it). Filtered against `config/qa.yaml` `banned_phrases`: read that list at run time and never use a
banned word even if it appears here or in the vendored files ("spearheaded" and "leveraged" are banned in
the shipped config). A verb must match the bullet's evidence (evidence_rules.md rule 6: no "led" when the
candidate supported).

- **Build:** Built, Developed, Designed, Implemented, Created, Launched, Shipped, Wrote, Deployed, Introduced
- **Improve:** Reduced, Cut, Improved, Optimized, Streamlined, Automated, Simplified, Accelerated, Refactored, Migrated
- **Scale:** Scaled, Grew, Expanded, Increased, Doubled
- **Analyze:** Analyzed, Profiled, Measured, Diagnosed, Investigated, Audited, Evaluated, Benchmarked
- **Fix:** Resolved, Debugged, Fixed, Eliminated, Prevented, Mitigated
- **Lead (own work only):** Led, Owned, Coordinated, Mentored, Directed, Organized
- **Collaborate:** Partnered, Collaborated, Presented, Documented, Contributed

## Weak openers

Never open a bullet with these (QA `bullet_shape` warns; the list lives in `config/qa.yaml`
`resume.soft.weak_openers`):

- `worked on`
- `helped`
- `responsible for`
- `assisted`
- `participated in`
- `involved in`
- `tasked with`

"Contributed to" is not weak when it is the honest ownership word (see Ownership honesty).

## Bullet shape

- **One idea per bullet.** One system, one result. Two results = two bullets.
- **About 15-28 words, 1-2 lines** on the one-page template. QA warns above `config/qa.yaml`
  `resume.soft.bullet_max_words` (35). Prefer a declared `variants.short` over a trimmed sentence when space
  is tight.
- **A number or a scale word** (users, requests, records, teams, services, daily, million, thousand, dozen)
  in most bullets. Soft target only; see OVERRIDE rule 4.
- **Name the technology** the posting cares about when the bullet's evidence has it (keyword mirroring
  follows evidence_rules.md rule 4).
- **Early-career tech section order:** contact line, optional one-line summary, Experience, Projects,
  Education, Skills. This is the shipped `config/qa.yaml` `resume.hard.section_order`, and that config value
  is the only thing that decides the order. With little work history, change it once in config (for
  example, projects ahead of experience) rather than per job. The vendored advice to put Technical Skills
  near the top is not used: the plain-text Skills section at the end parses fine for ATS.
- **Project format:** the entry's first bullet says what it does (the descriptive bullet, e.g.
  `widgetizer.1`), then the technical highlight (the hard part solved, with the tech named), then a usage
  metric if one exists in the profile (users, installs, requests). tailor-resume already keeps the
  descriptive bullet first.

## Ownership honesty

Team systems are described as "contributed to" or "member of", never "built", "designed", "led" or
"owned". Use the bullet's `ownership` field: `own` may use Build/Lead verbs; `team` uses "Contributed to
...", "As a member of the X team, ..." or a verb that names only the candidate's own part ("Wrote the retry
logic for ..."). This is evidence_rules.md rule 6 applied to wording: a stronger verb than the evidence is
unsupported even with a cited id.

## Choosing bullets and variants (tailor-resume)

1. Relevance first (tailor-resume section 2): a bullet that carries a `required_skills` term beats one that
   does not.
2. Among equally relevant bullets, prefer `resume_default: true`, then bullets with `metrics`, then the rest.
   Bullets flagged `weak: true` are used only when no other bullet covers that requirement or the entry
   would otherwise have no bullet.
3. Between a bullet's `text` and its `variants`, pick the one that best matches the tech bullet formula
   (verb first, technical what, scale, technology named) and fits 15-28 words; use `variants.short` when the
   page is tight. Never write a new variant; never change a number, tool or verb.
4. Display order within an entry: the project's descriptive bullet first, then the strongest
   formula-complete bullets (verb + what + scale + tech), then the rest.
5. For every included bullet with no number and no scale word, propose a metric question (OVERRIDE rule 2).
