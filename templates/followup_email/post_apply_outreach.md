# After applying: outreach to a recruiter, hiring manager or engineer

Send same day to 3 days after applying. Brief, straightforward, easy to read, humble: it should sound like a person,
not a status report ("I applied. <résumé line>. Could you...?" reads as robotic). At most 120 words before the sign-off.
LinkedIn variant: the same idea cut roughly in half (connection note <= 300 characters).
A candidate's own wording in `profile/voice/followups/post_apply_outreach.md` replaces this skeleton.

## Skeleton

```
Subject: [ROLE] at [COMPANY]

Hi [NAME],

I hope this message finds you well. I came across your profile and saw that you [WHAT THEY DO, plain words].
[WHY THAT CONNECTS TO ME, one honest line; recruiter: "so I thought you'd be the right person to reach out to."]

I recently applied to the [ROLE] role at [COMPANY]. I've been working on [WHAT I'VE WORKED ON, plain fact], so
[THEIR WORK, in their words] really interests me. I've attached my résumé in case it's helpful.

[ONE ASK, vary it; a referral only from employees, and not in every email:]
I'd be glad to connect briefly if you're open to it.
  / (Greenhouse) [COMPANY] uses Greenhouse, where referrals reach recruiters first. Would you be open to a brief chat
    about a referral, or to referring me directly? Totally understand if not.
  / Is there anything I could do to better position myself in the process?

Thank you,
<identity.name>
<identity.linkedin>
```

Humble always (user 2026-11-25): state what you've worked on as plain fact and let the reader judge the fit. Never
grade yourself ("great fit", "perfect fit", "ideal candidate"), never tell them what they want and then say it's you
("That's my day job"); qa.yaml `banned_phrases` fails these. Interest and gratitude, not claims. Say what the work
means, not the stack ("I work on software a bank runs on every day", not "I build Kafka services in Java"). No
résumé numbers, no phone number. Each fact still traces to a bullet id.

## Example

EXAMPLE (fictional candidate Alex Example).

```
Subject: Backend Engineer at Acme

Hi Dan,

I hope this message finds you well. I came across your profile and saw that you lead Acme's payments platform.
Payments are the kind of work I want to do.

I recently applied to the Backend Engineer role at Acme. I've been working on production software at a logistics
company, where I've learned a lot about keeping systems up, so the payments work on your team really interests me.
I've attached my résumé in case it's helpful.

I'd be glad to connect briefly if you're open to it.

Thank you,
Alex Example
linkedin.com/in/alex-example
```
(proof: initech.1, initech.2; background source: conference talk URL in contacts.json)

## Notes from public guides (2026-11-17)

- Referral asks: make it easy to say no ("totally understand if not"), and name the exact role with its link
  ([refer.me](https://www.refer.me/blog/how-to-get-a-job-referral-as-a-new-grad-with-zero-connections),
  [Happenstance](https://happenstance.ai/how-to/ask-someone-to-refer-you-for-a-job)).
- New grads can open with who they are ("I'm a recent <school> grad") before the role.
- Personalize each one; a copy-pasted ask reads as insincere
  ([EPAM](https://anywhere.epam.com/en/blog/how-to-ask-for-a-job-referral)).
