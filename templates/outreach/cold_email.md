# Cold email (engineer or hiring manager)

Sent via Gmail only after the candidate confirms the template (see TODO.md). Until then: draft in Contacts tab.
At most 80 words before the sign-off. Subject under 60 characters.

## Guidance

- Subject names the role or the thing you have in common. No "Quick question", no "Opportunity".
- Tone: warm, humble, easy to read; a friendly opener is fine. Sound like a person, not a status report.
- Why I'd fit: 2-3 short plain reasons (bullet ids, numbers intact, never stacked in one sentence).
- Ask: one. Call, referral, or "who should I talk to". For a referral from an employee (not a recruiter), ask them to
  submit it in the company's applicant system (the Greenhouse referral form when `posting.ats` is greenhouse, where referrals land in the recruiters'
  priority review queue; other ATS: their internal referral process, no priority claim). Keep the message at most 80 words (the sign-off is not counted).
- Close: "Thank you," then the full name from `profile/master.yaml: identity.name`,
  LinkedIn from `identity` under it. Never the phone number.
- Email address confidence must be `verified` or `pattern_match_high` before any auto-send.
- Nothing from `config/qa.yaml: banned_phrases`.

## Skeleton

Same shape as `templates/followup_email/post_apply_outreach.md` (warm greeting, "I'm reaching out regarding <role>",
2-3 plain reasons I'd fit, résumé attached, one varied ask, "Thank you," + name, LinkedIn; no phone). Open with one sourced line about the person's background or work.
