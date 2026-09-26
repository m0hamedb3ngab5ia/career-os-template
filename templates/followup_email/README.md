# Follow-up emails

Three core follow-ups, plus one optional. Structure and length guidance only; the wording comes from the
candidate's own versions in `profile/voice/followups/<type>.md` when present (use them as the base text and fill the
variables), else from the skeletons here.

| Type | File | When | Length | Sending |
|---|---|---|---|---|
| After applying | `post_apply_outreach.md` | same day to 3 days after applying | ~100 words (LinkedIn: ~half) | auto after the candidate approves the template, verified email only; otherwise a LinkedIn draft |
| After interview | `post_interview_thanks.md` | same day or next morning | 60-120 words | **always manual**: needs a real detail from the interview |
| No response | `status_followup.md` | 7-14 days after an interview or recruiter conversation | 40-70 words | auto after approval |
| After rejection (optional) | `after_rejection.md` | within a few days of a rejection | 40-70 words | manual, only if the candidate wants to keep the relationship |

## Rules for every follow-up

- **Follow-ups get shorter as the relationship gets stronger.** Initial outreach needs context and proof. The thank-you
  needs personalization. A status follow-up only needs interest and a polite request for an update.
- Variables: `[NAME]`, `[COMPANY]`, `[ROLE]`, `[SPECIFIC CONNECTION]`, `[MOST RELEVANT EXPERIENCE]`,
  `[SECOND RELEVANT SIGNAL]`, `[INTERVIEW DETAIL]`, `[WHAT YOU LEARNED]`, `[TECHNICAL CONNECTION]`, `[SPECIFIC TEAM/WORK]`.
  Fill them from the posting, `profile/master.yaml` (bullet/narrative ids only), interview notes in the job's `log.md`,
  and contact research (`contacts.json`). Never leave a bracket in a sent message; a variable with no source means
  the message goes to Action Items instead of out.
- Cold application with zero contact: one initial outreach plus at most one follow-up. Do not keep chasing.
- Recruiter found but no verified email: draft the LinkedIn variant of the after-applying outreach automatically.
  LinkedIn is always draft-only; the candidate sends.
- Every claim traces to a bullet or narrative id, numbers exact. Nothing from `config/qa.yaml: banned_phrases`.
