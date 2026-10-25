# apply-job: field-filling detail (section 3)

- Identity: `profile/master.yaml: identity` (split name on first space for first/last).
- Résumé: `file_upload` with `<job_dir>/resume.pdf`. After upload, verify the filename is shown. Two
  failures → Action Item type `other` "file upload failed", status needs_review, stop.
- Cover letter: paste `cover_letter.txt` into the manual-entry textarea; upload `cover_letter.pdf`
  only where no textarea exists. Skip entirely when tier says `if_required` and the field is optional.
- Every other field, by label text:

```python
from careeros.apply.questions import answer_for, classify_question
hit = answer_for(label, "profile/standard_answers.yaml", required=<field is marked required>, company=<posting company>)
```

  `company=` tries the answers learned for this company (`company_answers` block) before the general list.

  `answer_for` minimizes personal data: an optional street-address field stays blank; only a required
  one gets the street. Phone and email are the only other contact data given. A `sensitive` label never
  gets an answer (the field gate above already stopped the run).

  - hit with an answer → fill it. Apply the `note` rules from the YAML (referral name from
    Contacts tab; `previously_applied` = Yes if tracker shows this company applied).
  - hit with `None` answer (salary): if the control is a dropdown of ranges, pick the lowest bucket
    whose floor >= `config/targets.yaml: candidate.salary_dropdown_floor_usd`; if that key is missing,
    or the control is freeform, STOP → Action Item type `salary`, status needs_review.
  - no hit: `classify_question(label)`:
    - `eeo` → section 4.
    - `legal` → STOP, Action Item type `question` ("legal question not in standard answers: <label>"). Never guess.
      Every `question` / `salary` Action Item's text must contain the exact form question verbatim (`<class>:
      <question>` or `... : <label>`): `careeros action done <id> --answer "<text>"` learns the answer from it.
    - `essay` / `unknown` / `standard` → look up the `answers.json` entry (a JSON list) whose `question`,
      whitespace-collapsed and lower-cased, equals the label normalized the same way. Missing → run
      `/answer-question <job_dir> "<label>" --limit <maxlength>` per
      `.claude/skills/answer-question/SKILL.md`. If it returns `needs_review` with a non-null `answer`
      (class `standard` / `essay`, e.g. tier A flags every answer) and `auto_submit` is false (assisted mode,
      `CAREEROS_AUTO_SUBMIT=0`): fill that best-effort answer, keep `needs_review: true` on its `answers.json`
      entry and list the question in the "Review & submit" Action Item text (section 5) so the candidate checks
      it before submitting. Otherwise (`answer` null: class `sensitive`, `salary_freeform` or `unknown` with
      nothing to fill; or `auto_submit` true) → STOP, leave the field blank, screenshot, Action Item type
      `question`, status needs_review.
  - Respect `maxlength`; an over-limit answer is a STOP (type `question`).
- After filling any field, record what went in: `s.record_field(label, value, source)` with `source` one of
  `profile`, `standard`, `eeo`, `essay`, `salary`, `upload` (for uploads the value is the file name). These
  values are kept in the as-submitted snapshot (section 5). Secrets are never recorded: do not pass a
  password (e.g. the Workday account password), a verification or one-time code, a security question
  answer, a token or an API key to `record_field` or `--answers-json`, and never write them in `s.step`
  notes, `log.md` or the RESULT line. As a backstop, `record_field` and `freeze` store `<redacted>` for any
  label matching `careeros.apply.session.is_secret_label`.
- After each page/step in multi-page flows: screenshot, `s.step`.
