# Chat instead of clicking

The web UI (`careeros ui`) is a read-only dashboard: **Today** and **Jobs** (table, board, ticking). Everything else is done in Claude Code chat, with the skills in `.claude/skills/` and the `careeros` CLI (`docs/COMMANDS.md`). Decision: DEC-024.

| You used to click | Say, or run now |
|---|---|
| Settings | "change `<key>` in `config/<file>.yaml` to `<value>`"; `careeros doctor` checks the result |
| Job detail (documents, status, safety, score) | `careeros job show <id>` (`--full`), or "show job `<id>`"; status: `careeros job status <id> <status>` |
| Job detail › fill plan, apply session | `careeros apply plan <id>`, review `fill_plan.json`, then `careeros apply fill <id>` (Playwright); `/apply-job` for the Chrome path |
| Automation / Runs, run detail | `careeros run list`, `run show <id>`, `run status`, `run pause` / `run resume` |
| Start pipeline (Jobs page) | tick jobs in Jobs, then `/prepare-job <id>` or `careeros batch create` + `batch run` (`batch show` for progress) |
| Batch progress page | `careeros batch show <id>`; `batch pause`, `batch cancel`, `batch retry` |
| Check a job (paste or upload a posting) | paste the posting in chat and run `/score-job`; then `/prepare-job` |
| Profile | "edit `profile/master.yaml`: ..."; `/extract-master` after a master résumé is stored; `careeros doctor` |
| Standard answers page | `careeros learn answer "<question>" "<answer>"`, `learn list`; or edit `profile/standard_answers.yaml` |
| Résumé upload, list, versions | `careeros resume add <file>`, `careeros resume list` |
| Résumé review | `/review-resume <rid>` |
| Résumé workspace (edit, apply a suggestion, reply) | `/edit-resume <rid> <aid>`; or ask in chat to change a bullet; `careeros resume annotations <rid>` lists the cards |
| Résumé match / reuse | `careeros resume match <id>`, `careeros resume pick <id>` |
| Action Items page | "what needs me?"; `careeros action list`, `action add`, `action done <id>` |
| Inbox | `/inbox-sync` |
| Contacts, Drafts sheet | `/find-contacts <id>`, `/draft-outreach <id>` (draft only, never sent); `careeros outreach check` |
| Writing samples (Profile) | put files in `profile/voice/samples/`, run `/learn-voice` |
| Component kit, onboarding Tour | none; read `docs/GETTING_STARTED.md` |
| Today (needs-you, top picks) | still in the UI; in chat: `/today` (read-only) |

New chat skills (DEC-024):
- `/advice`: paste outside advice, get a verdict adopt / park / reject with evidence; logged to `.agent/ADVICE.md`.
- `/today`: the dashboard in chat, read-only.
- `/interview-prep <id>`: writes `interview_prep.md` in the job folder from `profile/master.yaml` bullet ids.
- `/score-job` now also writes `gaps[]` (stated requirements the profile does not evidence, plus logistics (start date, relocation, on-site)).

Hard rules still apply in chat: no fabricated résumé facts, no guessed legal or salary answers, nothing submitted for Tier A.
