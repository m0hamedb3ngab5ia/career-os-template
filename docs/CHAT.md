# Chat instead of clicking

You never need to remember commands: say what you want and Claude runs them. The commands below are for reference.

The web UI (`careeros ui`) is a read-only dashboard: **Today** and **Jobs** (table, board, ticking). Everything else is done in Claude Code chat, with the skills in `.claude/skills/` and the `careeros` CLI (`docs/COMMANDS.md`). Decision: DEC-024. The whole path from onboarding to follow-ups is in [PROCESS.md](PROCESS.md).

| You used to click | Say, or run now |
|---|---|
| Which filters exist, what each removed | the Search tab of `careeros view`; say e.g. "Only jobs posted in the last 14 days" or "Only remote and hybrid jobs" and Claude edits `config/targets.yaml` |
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
| Cold outreach for my best applications | "draft outreach for my top 3" → `careeros outreach targets --top 3`, then `/find-contacts <id>` and `/draft-outreach <id>` per job; emails: `careeros outreach emails <id>` |
| Referrals (who do I know at these companies?) | drop LinkedIn's `Connections.csv` in, "import my network" → `careeros network import <csv>`; `careeros network match`; `/today` lists them; `/draft-outreach <id>` drafts the ask |
| Writing samples (Profile) | put files in `profile/voice/samples/`, run `/learn-voice` |
| Component kit, onboarding Tour | say "set me up" (`/onboard`), or read `docs/GETTING_STARTED.md` |
| Add companies / job sources | "add <company>": `careeros company find-board "<name>"`; "job alerts": `/job-alerts` (LinkedIn alert emails → boards) |
| Today (needs-you, top picks) | still in the UI; in chat: `/today` (read-only) |

New chat skills (DEC-024):
- `/advice`: paste outside advice, get a verdict adopt / park / reject with evidence; logged to `.agent/ADVICE.md`.
- `/today`: the dashboard in chat, read-only.
- `/interview-prep <id>`: writes `interview_prep.md` in the job folder from `profile/master.yaml` bullet ids.
- `/score-job` now also writes `gaps[]` (stated requirements the profile does not evidence, plus logistics (start date, relocation, on-site)).

Changing your mind (Claude edits files or runs existing commands; you only say it):
- "Don't apply to `<company>`": Claude adds it to `config/companies.yaml: blocklist.companies` (keeping comments) and sets that company's open jobs (found, scored, queued, needs_review) to skipped with `careeros job status <id> skipped --note blocklist`. Scout and score-job keep enforcing the blocklist. "Unblock `<company>`" reverses it.
- "This posting is fine" / "mark safe": `careeros safety clear`, then `careeros job status <id> queued`.
- "Close these action items": `careeros action done <id>` for each id.

Hard rules still apply in chat: no fabricated résumé facts, no guessed legal or salary answers, nothing submitted for Tier A.
