# Résumé references (shared by tailor-resume, review-resume, edit-resume, qa-review)

What strong senior and backend bullets look like in public examples and advice. General guidance only. It adds
to `.claude/skills/_shared/resume_writing_rules.md` (formulas, power verbs, weak openers, ownership, bullet
shape, entries) and never replaces it: where this file and the rules disagree, the rules win, then
`profile/resume_feedback.md`, then `.claude/skills/_shared/evidence_rules.md`. Everything here is about
wording and shape. Facts and numbers come only from `profile/master.yaml`.

## Hard limits on how to use it

- **Numbers come only from the profile.** Several sources suggest estimating a figure or rounding up. In
  career-os that never applies: a bullet without a number gets a metric question (rules.md, OVERRIDE rule 2),
  and the candidate answers it. Do not infer a figure from a role's seniority, a company's size or a "typical"
  result.
- **Example bullets below are fictional shapes.** Never copy their facts, tools or numbers into a draft.
- **Never copy wording from a real person's résumé.** Copy the structure, not the sentences.

## What senior and backend bullets do

- **A short scope line, then about five bullets.** The strongest examples open each role with one line of
  business context and scale (what the system does, who uses it, how big it is), then give bullets that add
  detail. Use only if the profile holds that context for the entry.
- **Action, system, result.** The verb names the candidate's move, the object is a real system or
  component, the ending is what changed for the business or the users.
- **Scale appears twice.** Once as context ("a system handling X"), once inside a bullet's result. A number
  in a bullet is clearest next to what it measures: latency, uptime, volume, duration, cost, error rate.
- **Before and after beats a lone number.** "Down from A to B" shows the change; "improved by 30%" only the
  size. Use the pair only when the profile holds both.
- **Tech is named inside the sentence**, tied to the job it did ("a Kafka pipeline that ...", "Redis caching
  in front of ..."), not only in a skills list. A tech list at the foot of a project is acceptable when the
  bullets already name the key ones.
- **Senior reads as ownership and reach, not task count.** Look for: design decisions and their reason,
  migration or rollout, reliability and observability standards, security, compliance, reviews and mentoring,
  influence across teams that depend on the system. Honest wording still follows rules.md "Ownership
  honesty": a team system is "contributed to", not "owned".
- **Fewer bullets per role as roles get older.** Recent role gets the most room; roles older than about ten
  years get a line or two, or only the heading.
- **Operational and quality outcomes count** when real: test coverage, failure recovery, on-call load, defects
  caught, deploy time. Pair them with what they protected.

## How to quantify honestly

- **Pick the metric that fits the work.** Backend: latency, throughput, uptime, error rate, cost, deploy or
  recovery time. Data and ops: volume, accuracy, hours saved, cycle time. Teams: size, scope, people mentored.
- **Scale or relative words when the exact figure is private**, only if the candidate used them: "high-traffic",
  "multi-region", "halved". The candidate states them; a skill never upgrades a vague bullet into a precise one.
- **No exact figure and no safe word: ask.** Add a metric question for the bullet (rules.md OVERRIDE rule 2).
  Good questions are concrete: a count, a before and after, a frequency, a volume. Never suggest the answer.
- **Candidate estimates are marked** with `~` and `estimate: true` (rules.md OVERRIDE rule 3).
- **Not impact:** lines of code, PR counts for client work, "significantly improved", results the candidate
  did not drive, lists of duties with no outcome.

## Patterns to copy

1. Scope line, then bullets that each add a new fact (no restating the same win).
2. Verb first, system second, result last; tech named where it did the work.
3. One bullet per distinct system or decision.
4. A reliability or compliance bullet next to the feature bullets (shows judgment, not only output).
5. One leadership or review bullet for senior roles when it is true.
6. Concrete nouns an outsider knows (payments, orders, reports), internal names dropped.

## Anti-patterns

- Duty lists ("responsible for", "worked on"), see rules.md weak openers.
- A tool list with no sign of what it was used for.
- Seniority claims without evidence: "led", "architected" on team work.
- Numbers with no unit or no baseline ("improved performance by 30%" with nothing measured).
- Two results stacked into one long bullet; a bullet past about 28 words.
- Same verb opening several bullets in a row; same metric reused across bullets.
- Padding a thin entry with tool names instead of cutting it.

## Illustrative shapes (fictional; shapes only)

- Scope line: "Order-matching service for a retail marketplace; N requests per day across M regions."
- "Cut report generation from A minutes to B by moving nightly jobs onto a queue-based pipeline in Python."
- "Replaced a polling integration with Kafka events, so downstream teams saw updates in seconds, not hours."
- "Added retry and dead-letter handling to an event consumer, removing a weekly manual replay."
- "Contributed to a payments ledger as a member of a four-person team; wrote the reconciliation checks."
- "Designed zero-downtime schema migrations for a PostgreSQL table with N rows, run with no customer impact."
- "Introduced tracing and dashboards for a service chain, shortening incident diagnosis from hours to minutes."
- "Mentored three engineers through design reviews for a shared platform used by N teams."
- "Added request signing and role checks to internal APIs, closing a gap an audit flagged."

Each placeholder (N, M, A, B) must come from the profile or become a metric question.

## Approved examples

If `profile/resume_examples/` has files, read its README.md and compare the draft against the approved
example(s) for tone, density and quantification. Never copy facts from them that are not in `master.yaml`.

## Sources

- https://www.techinterview.org/post/3233474604/quantifying-impact-engineering-resume/ (action, scope,
  outcome; approximate scale; vanity metrics)
- https://enhancv.com/resume-examples/backend-engineer/ (scope line, verb plus tech plus result, senior focus)
- https://arbaz4sayyad.github.io/resume/Arbaz_Sayyad_Software_Engineer_Backend_Resume.pdf (backend bullets:
  volume, retry and failure handling, coverage; structure only)
- https://gauravratnawat.github.io/Gaurav%20Ratnawat%20Lead%20Engg%20Resume.docx.pdf (lead-level project
  bullets: ownership, volume, uptime, compliance, mentoring; structure only)
