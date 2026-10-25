# apply-job: login detail (section 2a)

Logins come only from the credentials store (`.venv/bin/careeros creds get`, file `paths.credentials`, default
`~/.careeros/credentials.yaml`, outside the repo). Site key = the ATS (`workday`, `greenhouse`, `lever`, `ashby`) or
a per-tenant key the candidate chose (`.venv/bin/careeros creds list` shows them, no secrets).

1. `.venv/bin/careeros creds get <site> --json` → `username`, `notes`, `has_password`. Unknown site or `has_password: false`
   → STOP, Action Item type `laptop_required` ("add a login: `.venv/bin/careeros creds set <site> --username ...`"), needs laptop.
2. Type the username. For the password field only: `.venv/bin/careeros creds get <site> --reveal` and type its output
   straight into the field. Never print, echo, quote or summarise it; never put it in `record_field`,
   `--answers-json`, `s.step`, `log.md`, `posting.json`, `status.json`, screenshots taken with it visible
   (mask the field first) or the RESULT line. Credentials are never copied into `data/jobs/` or `profile/`.
3. Login rejected, MFA or a one-time code → STOP (section 6 rules), Action Item; never retry more than once.
