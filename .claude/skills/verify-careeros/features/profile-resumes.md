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

## Driving it (user mode, Playwright)

Preconditions: baseline from `README.md`; no résumé stored (`curl -s 127.0.0.1:8799/api/profile/resumes` returns `{"resumes":[]}`). Fixture: `tests/fixtures/voice_sample.docx` (tracked).

- **Upload.** `drive.py` steps: `goto /profile#resumes` (expect `Upload résumé`), skip tour if shown, `set_input_files("input[type=file]", "tests/fixtures/voice_sample.docx")` (expect `voice_sample · master`, the refreshed list row). Page lists `voice_sample · master · v1`, `Master`, `Delete`.
- **Listed.** Reload `/profile#resumes`; same row. Also `The review failed. Retry review` without `claude`.
- **ATS view (dev API read; no UI panel).** `GET /api/profile/resumes/<rid>/versions/1` returns `text` and `ats.fields` + `ats.warnings` (the fixture gives `missing contact (no email or phone)`).
- **Side effects (disk check).** `ls profile/resumes/<rid>/v1` shows `original.docx text.txt ats.json`.
- **Review (not proven).** With no `claude` the run ends `doctor_failed` (`GET /api/runs/<review_run>`), UI shows `The review failed.` and `Retry review`. With `claude`, items appear under `Feedback: N open of M`; `Apply` on an item adds v2 (`POST .../feedback/<id>/apply`).
- **Make master / delete.** Upload a second file, click `Make master`; `Delete <name>` asks `Delete <name>?` then confirms. Undo by deleting the rows you made.
- **Proof.** Save upload response, list JSON, version JSON, `steps.jsonl`, screenshots in `$EV`.

## Driving it (dev mode, API)

`curl -s -X PUT -H 'X-CareerOS: 1' --data-binary @tests/fixtures/voice_sample.docx "http://127.0.0.1:8799/api/profile/resumes?filename=voice_sample.docx"` returns `{"rid":...,"n":1,"review_run":...}`. `GET /api/profile/resumes` lists it; `GET /api/profile/resumes/<rid>/versions/1` has `text`, `ats.fields`, `ats.warnings` (`missing contact (no email or phone)`); `ls profile/resumes/<rid>/v1` = `original.docx text.txt ats.json`. Review run ends `doctor_failed` (`GET /api/runs/<review_run>`) without `claude`.

## UX checks

- One obvious next action per screen: `Upload résumé` first, then review.
- Steps to value: clicks from `/profile` to a listed master (TTA).
- Wait shows progress: upload and review states visible, not silent.
- Error shows a fix: `The review failed. Retry review` names the action; refused file type says what is accepted.
- File picker offers .txt/.md that the API refuses (errors prevented, not just reported).
- Checklist items (`Fix`) link to where to fix.

## Gotchas

- `.txt`/`.md` pass the picker but the API refuses with `only PDF or DOCX résumés are accepted`.
- Uploading the first résumé makes it master and also triggers extract-master (`master.yaml sync` card shows "Couldn’t read your master résumé. Re-read" without `claude`).
- Max 5 MB. Hidden file input: `set_input_files` works on it; no click on the button needed.
- Tour popup covers the page on first load.
