# Profile › Résumés

A user uploads a PDF or DOCX résumé; it is stored as a versioned résumé (first one becomes master), shown in the Résumés list, parsed into an ATS view, reviewed by an LLM for feedback items, and edited through suggestion apply.

## Sub-features

- `resume-upload` upload a PDF/DOCX; listed as `<name> · master · v1`.
- `resume-ats` per-version extracted text + ATS fields and warnings (API only; no UI panel found).
- `resume-review` upload starts a review; feedback shows as `Feedback: N open of M` (needs `claude`).
- `resume-apply` apply a suggestion creating a new version (needs `claude`).
- `resume-versions` versions list and per-version read.
- `resume-master` `Make master` on non-master; `Delete` with confirm.

## How to get to it (user POV)

- Sidebar `Profile`, then section `Résumés` (`/profile#resumes`).
- Button `Upload résumé` (accepts .pdf .docx .txt .md in the picker, but the backend only stores PDF/DOCX).
- Button `Retry review` after a failed review.

## Driving it with browser MCP + curl

Preconditions: baseline from `README.md`; no résumé stored (`curl -s 127.0.0.1:8799/api/profile/resumes` returns `{"resumes":[]}`). Fixture: `tests/fixtures/voice_sample.docx` (tracked).

- **Upload.** `curl -s -X PUT -H 'X-CareerOS: 1' --data-binary @tests/fixtures/voice_sample.docx "http://127.0.0.1:8799/api/profile/resumes?filename=voice_sample.docx"` returns `{"rid":"voice-sample-xxxx","n":1,"review_run":"..."}`. Save rid.
- **Listed.** `navigate http://127.0.0.1:8799/profile#resumes`, `Skip tour`, `get_page_text`. Section `Résumés` shows `voice_sample · master · v1`, `Master`, `Delete`. API: `GET /api/profile/resumes` has the same row.
- **ATS view.** `curl -s 127.0.0.1:8799/api/profile/resumes/<rid>/versions/1` returns `text` and `ats.fields` + `ats.warnings` (the fixture gives `missing contact (no email or phone)`).
- **Side effects.** `ls profile/resumes/<rid>/v1` shows `original.docx text.txt ats.json`.
- **Review (not proven).** With no `claude` the run ends `doctor_failed` (`GET /api/runs/<review_run>`), UI shows `The review failed.` and `Retry review`. With `claude`, items appear under `Feedback: N open of M`; `Apply` on an item adds v2 (`POST .../feedback/<id>/apply`).
- **Make master / delete.** Upload a second file, click `Make master`; `Delete <name>` asks `Delete <name>?` then confirms. Undo by deleting the rows you made.
- **Proof.** Save upload response, list JSON, version JSON, page text, screenshot in `$EV`.

## Gotchas

- `.txt`/`.md` pass the picker but the API answers 400 `only PDF or DOCX résumés are accepted`.
- Uploading the first résumé makes it master and also triggers extract-master (`master.yaml sync` card shows "Couldn’t read your master résumé. Re-read" without `claude`).
- Max 5 MB. Native file input cannot be filled by the browser MCP; use curl.
- Tour popup covers the page on first load.
