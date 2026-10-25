# apply-job: safety gate detail (section 1b)

Code: `src/careeros/safety/` (scam, company risk, ghost jobs). Every check yields a reason code, a level
and evidence; the verdict is **pass**, **review** or **block** (`skip` for dead postings).

1. Posting gate, before opening the browser: `.venv/bin/careeros safety check <job_id>`, then read
   `safety.json`:
   - `verdict` block (exit 3) or skip (exit 4): stop. The CLI already opened the Action Item / set the
     status. Print `RESULT` with `outcome: failed`, reason `safety <verdict>: <codes>`.
   - `verdict` review: continue in assisted mode only (`auto_submit` false; stop before submit with a
     `review` Action Item naming the review codes). Never auto-submit a review job.
   - `verdict` pass: `auto_submit_allowed` feeds the preconditions table.
2. Field gate, on every page/step of the form: collect every visible field label, placeholder and upload
   prompt after `read_page`, then
   `echo '<JSON list of labels>' | .venv/bin/careeros safety fields <job_id> --labels-json - --page-url <current url>`.
   Exit 3 (block): SSN / national ID, date of birth, bank numbers, passport or ID uploads, driver's
   license, mother's maiden name (allowed only once status is `offer`); any fee or card number; passwords,
   security questions or codes for another account (creating a password or entering an emailed code on the
   ATS's own domain is normal); remote-access software. Work-authorization questions are normal.
3. A redirect to a domain other than the apply URL's, the company's or a known ATS: stop and run
   `careeros safety flag "<company>" --domain <host> --confidence medium --reason "redirect to <host>" --evidence <url>`.

On exit 3 from step 2:
1. Do not enter anything further.
2. `s.step("safety_gate", False, "<first flag line>")`, save the session, print `RESULT` with
   `outcome: failed`, reason `safety block: <codes>`, then close the tab.

The user reviews the item by hand; the gate is never overridden from inside this skill (clearing a
company is `careeros safety clear <company> --note ...`, run by the user).
