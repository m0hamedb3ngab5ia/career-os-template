# Decisions (product)
Repo-wide stable decisions: `.agent/DECISIONS.md`. This file: DEC entries from /product stages.

### DEC-001 Text extraction: pypdf + stdlib docx
Decision: PDF via `pypdf` (move from test extras to core deps); DOCX via stdlib `zipfile` + `xml.etree` on `word/document.xml`; txt/md read as UTF-8. Same extractor feeds ATS view (REQ-098) and match (REQ-111).
Reason: pypdf pure-Python, already used in tests; DOCX text is one XML file.
Alternatives: pdfminer.six (heavier), python-docx (dep for one file read), LLM extraction (non-deterministic).
Consequences: scanned/image PDFs → "no text found" warning, match 0. No OCR.

### DEC-002 Injection scan at Store.save_posting, flags in flags.json
Decision: `careeros.untrusted.scan(text, html)` runs inside `Store.save_posting` (single path for scout, Check a job, import). Patterns: instruction phrases (`ignore (all |the )?(previous|prior|above) (instructions|prompts?)`, `disregard (all )?(the )?(previous|prior|above)`, `system prompt`, `you are now (a|an|in|the)`, `as an AI (language )?model`, `new instructions`; any whitespace between words), zero-width/bidi chars (U+200B-200F, 202A-202E, 2060-2064, FEFF), CSS-hidden text, `font-size:0`, and white/transparent text with no visible (non-white, non-transparent) `background` in the same style in raw HTML; tool/command names (`Bash`, `WebFetch`, `WebSearch`, `curl `, `mcp__`, `careeros `) and mailto/emails count only inside a sentence with an instruction phrase (amended 2026-10-04: "Strong Bash skills" is a normal posting). Invalid `extra_patterns` regexes are skipped with a warning. Hit → `flags.json` + Action Item. Patterns in code, extendable via `config/pipeline.yaml: injection.extra_patterns`.
Reason: one choke point; deterministic; cheap.
Alternatives: LLM classifier (costs a run per job, injectable itself).
Consequences: false positives cost one "I checked it" click.

### DEC-003 Match score formula
Decision: `match = 100 * (0.7*req_cov + 0.2*pref_cov + 0.1*title_cov)`, weights renormalised over non-empty groups. Skills = `score.json` required_skills / nice_to_have_skills (one LLM score per job, then deterministic); title terms = posting title tokens minus stopwords. Term hit = `qa._term_in_text` with qa's variants (moved to shared `careeros.terms`). Résumé text = `extract` output (REQ-098).
Reason: Q-018 deterministic; reuses QA keyword logic so QA and match agree.
Alternatives: embeddings (dep + non-explainable), LLM rank (cost).
Consequences: synonyms not matched ("k8s" vs "Kubernetes") unless listed in `config/pipeline.yaml: match.synonyms`.

### DEC-004 Readiness: one module, exit 7
Decision: `careeros.readiness.items(root)` builds the list from doctor checks + profile state; `careeros doctor`, `GET /api/readiness` and `require_ready()` (raises `NotReady` → CLI exit 7 / API 409) share it. Called in `apply plan|fill`, `run apply`, batch stage fill|submit, tick apply.
Reason: one source; doctor already holds the example/placeholder checks.
Consequences: exit 7 newly reserved (6 = lock held, 3 = conflicts/sensitive).

### DEC-005 Per-kind tool lists (prompt injection)
Decision (REQ-108): `score`, `review`, `resume_edit`, `extract_master`, `learn_voice`: no WebSearch/WebFetch. `prepare`: WebSearch + `WebFetch(domain:<company domain>)` only (domain from posting company URL / ATS board), for the letter's sourced company facts. `apply`: unchanged (Chrome).
Reason: write-cover-letter needs ≥2 sourced company facts; domain-scoped fetch blocks exfil to attacker URLs.
Alternatives: no web in prepare (letters lose sourced facts, change write-cover-letter); unrestricted (today).
Consequences: REQ-108 amended 2026-10-04 (user approved at arch gate). Residual: WebSearch queries reach the search provider.

### DEC-006 Uploads as raw request body
Decision: `PUT …?filename=` with raw bytes; size checked by Content-Length + streamed cap; type by extension + magic bytes (`%PDF`, `PK`).
Reason: FastAPI multipart needs `python-multipart`; one dep avoided.
Consequences: UI uses `fetch(url, {method:'PUT', body:file})`.

### DEC-007 Reused user-authored résumé skips bullet-trace QA
Decision: when `resume_choice.action = reuse` and the version author is `user` (upload/edit), QA skips bullet-id checks (truth_trace, bullet_fidelity, numbers vs master) and runs the rest (confidential, untrusted_content, contact, pdf, keyword coverage). AI-authored versions keep full QA.
Reason: REQ-097 — user owns facts in their own résumé; bullet ids don't exist there.
Consequences: a user-typed fabrication passes QA; that is the user's call.

### DEC-008 Résumé store under profile/resumes
Decision: layout in 09_ARCHITECTURE.md delta "Storage layout"; `rid` = server-generated slug + 4 hex; tailored/tweaked outputs saved as `type: tailored` résumés with `category` (score category) so later jobs reuse them.
Reason: profile/ already gitignored and `--link`-able to the private repo; résumés are profile data.
Consequences: `careeros prune` never touches profile/resumes.

### DEC-009 Minimal UI: only what an approved REQ needs
Decision: IA + UX are the minimum that meets approved REQs/UCs/FLOWs, nothing more. Every screen, section, control and dialog cites a REQ/UC/FLOW in 06_IA.md; anything in the current UI without one is a removal candidate (06_IA.md "Trim list"), removed before or alongside frontend TASKs, never extended. Visual/interaction quality follows Vercel Web Interface Guidelines (`web-design-guidelines` skill audit per frontend PR).
Reason: current UI grew well beyond the requirements (user, 2026-10-04); every extra surface costs build, test and review.
Alternatives: keep current UI and add delta on top (more slop); full redesign now (unscoped).
Consequences: frontend TASK-013..015 start with a trim pass; new UI needs a REQ first (`/product change`). Not implemented yet: recorded before development.

### DEC-010 AI-drafted form answers need review before fill
Decision: fill plan uses the job's `/answer-question` drafts for freetext fields with no saved answer, source "AI draft", unreviewed until the user approves or edits it; fill refuses unreviewed drafts. Save-to-profile off by default for drafts.
Reason: user wants drafts offered but reviewed before fill (2026-10-04). Reasoned by: human (gate); agent (accepted) for edit = reviewed, save default off, Action Item.
Alternatives: drop "AI draft" from REQ-105 (user types every essay); auto-fill drafts (unreviewed AI text reaches employers).
Consequences: new TASK-023; TASK-014 tests re-reviewed for the draft source.

### DEC-011 Minimize time to value (TTV/TTA)
Decision: users have limited time, patience, attention. Every screen, interaction and workflow either produces value or brings the user visibly closer to it. Prioritize simplicity, sensible defaults, minimal user effort, immediate feedback. Eliminate unnecessary decisions, steps, complexity. Slow process: show progress and what to expect.
**The goal is not simply to make the application faster, but to minimize the time and effort between a user's intent and a meaningful result.**
- TTV (Time to Value) = intent -> first useful visible result.
- TTA (Time to Action) = time and effort to identify and take the next meaningful action in an interface. Not "time to apply".
- Targets are design targets, not guarantees. Meaningful results over arbitrary speed. No promises dependent on external sites, AI processing or job availability. Validate with real users; measure TTV/TTA.
- Review gate: every UI PR answers "does this add a step, screen, decision or wait before value?" (`docs/CODE_REVIEW_PROMPT.md`). Yes = justify and weigh simpler options; added friction is acceptable only when it improves accuracy, safety, clarity or user control. Every added interaction must earn its place.
- Decision rule between designs, in order: value sooner; less user effort; clearer next action; accuracy, transparency and control preserved. Fewer clicks alone is not better UX.
- Applies at every stage: requirements (outcome + TTV/TTA target), design, build, test (measure real TTV/TTA, recovery, understanding), review (gate), iteration (cut observed friction).
- North star: CareerOS does the work so the user focuses on getting hired, not operating the software.

TTV targets (aggressive, but optimize for meaningful value, not fewer clicks):

| Area | Target |
|---|---|
| a. Getting started | First résumé feedback within 5 min, no edits required. Upload is the primary action; skipping allowed for exploration. |
| b. Finding jobs | Scored jobs in same session. Keep/skip in one click. Show why each job matches. |
| c. Preparing | Initial fit score within seconds; review-ready docs within minutes. Approve or open editor in one action. |
| d. Applying | 30 s of user interaction, excluding external site delays. Fill in one action, review, then submit. Never sacrifice accuracy. |
| e. Running on its own | One-action setup with sensible defaults. Results ready on next visit, with clear progress, errors, actions needing approval. |
| f. Profile | Never re-request info already given unless outdated, missing or needing confirmation. Reuse across workflows. |
| g. Settings | No settings before first value. Sensible defaults; introduce configuration when relevant. |
| h. Staying on top | To-do list immediately on open. Highest-impact actions first. |
| i. Recovering from interruptions | Leave and return without losing progress. Every workflow resumes where it stopped, with a clear next action. |

Fluff rules:

| Rule | Meaning |
|---|---|
| Defaults over questions | Reduce decisions. Allow overrides. |
| Defer setup until needed | Value before configuration. |
| Progress, not spinners | Progress for longer tasks; spinners fine for brief waits. Never fake progress. |
| Undo over confirm | Undo for reversible actions. Confirm irreversible/high-risk ones, esp. submitting applications. |
| Every screen has a purpose | Needs a clear purpose, not necessarily an action. |
| Minimize user input | Reuse existing data. Automate repetitive work. |
| Progressive disclosure | Essentials first; complexity when needed. |
| Clear, concise language | Plain language. No jargon, redundant explanations, lengthy instructions. |
| Preserve user progress | Auto-save. Resume interrupted workflows. |

Reason: user stated principle 2026-10-11. Reasoned by: human.
Consequences: UI work (with DEC-009) is judged against these targets; a UI PR that adds a step/screen/wait before value needs justification.

### DEC-012 Résumé workspace: one page, our format, one version per sitting
Reasoned by: human (feedback 2026-10-11 §1, answers 2026-10-12)
Decision: every upload converted into our structured résumé + LaTeX template; original file = v1 read-only. Own full-page workspace (`/resumes/<rid>`); Profile keeps a one-line row. Feedback = Google-Docs-style suggestions: hover highlights the quoted text, Accept replaces in place, Revert via History bin (+ ⌘Z). Autosaved draft server-side; one version per Next/Done (per-change author ai|user, "you + AI"); leaving keeps draft, row shows "Draft". Open suggestions never block Next. Version history = "Show changes" inline diff, no Compare picker. Preview = HTML render (instant, no LaTeX); PDF via LaTeX when present. Conversion guarded (no new facts) + "Not carried over" list with Restore.
Why: user could not see where feedback applies, what changed, or the new version ("Applied v8" with no v8). TTV/TTA (DEC-011): value visible in place, no hunting.
Amended 2026-10-12 (wireframe review, human): Save/Discard bar → autosave; per-card Undo → History + Revert; Compare dropped (not important); red/green → one AI colour.
Rejected: keep user's own layout (can't edit or diff reliably); version per accept (noise, 8 versions per sitting); side-by-side compare; live PDF preview (slow, needs LaTeX).

### DEC-013 Structured résumé is the source of truth, stored as files
Reasoned by: human (2026-10-12; agent critique accepted: files not tables, text.txt derived)
Decision: each résumé's canonical content = structured JSON (DEC-018 schema), stable ids for sections, entries, bullets. Published versions `v<n>/resume.json`; the working draft `<rid>/draft.json`. One rendering pipeline: PDF (`templates/resume/render.py`) and HTML preview read the JSON. `v<n>/text.txt` + `ats.json` are regenerated from the JSON on publish (match + extract-master keep reading text).
Why: editing, diffing, suggestions and revert need addressable parts; free text can't target a bullet.
Alternatives: SQLite tables (rejected: `data/careeros.db` is a disposable index, profile data lives in `profile/` and syncs to the private repo); phase out text.txt (rejected: match/ATS read it).
Consequences: uploads must be converted (DEC-019); old text-only versions stay readable, get JSON on next import.

### DEC-014 One autosaved draft per résumé; "Draft" = content differs
Reasoned by: human (2026-10-12; agent critique accepted: label by hash)
Decision: one `draft.json` per résumé. UI saves 500–800 ms after the last keystroke and flushes on navigation/unload. Every save carries the draft's `rev`; server rejects a stale `rev` (409, reload). Profile row shows "Draft" when hash(draft) ≠ hash(latest version), so edit-then-undo clears it.
Why: no lost edits without a Save button (DEC-012); two tabs can't overwrite each other silently.
Alternatives: label on any save (sticky false "Draft"); last-write-wins (loses edits).

### DEC-015 History = append-only change log; revert is a new change
Reasoned by: human (2026-10-12; agent critique accepted: no snapshots, conflict rule)
Decision: `draft.changes.jsonl`, one line per change `{id, at, author ai|user, target_id, op, before, after, reverts?}`; starts at the draft's base version. ⌘Z = short-lived client undo stack, separate from History. History Revert appends an inverse change, never deletes; allowed only when the target still holds the change's `after`, else refused with both texts shown.
Why: auditable reverts; revert must never wipe a later edit.
Alternatives: periodic snapshots (not needed: résumé ~5 KB, each version is a full copy; add only if replay is slow); event sourcing / CRDTs (no multi-user requirement).

### DEC-016 Suggestions and comments: one annotation model, AI only proposes
Reasoned by: human (2026-10-12; agent critique accepted: `base` field, fabrication guard)
Decision: `<rid>/annotations.json`, items `{id, kind suggestion|comment, target_id, base, author, status open|accepted|rejected|outdated, proposed, text, replies[], at}`. `base` = target text when made; target changed → `outdated`. AI (review-resume, Apply-comment run) reads the résumé + annotations and writes only proposals and replies. Accept = a user action that goes through the existing `apply-edit` base check and zero-fabrication guard, then logs a change (DEC-015).
Why: no silent AI changes; replaces `review.json` items with one model.
Alternatives: AI edits draft directly (violates hard rule: no unreviewed AI résumé changes).

### DEC-017 Version on Next/Done: atomic, idempotent, nothing discarded
Reasoned by: human (2026-10-12; agent critique accepted: no-op on unchanged hash, idempotency key)
Decision: Next/Done publishes `v<n+1>` atomically (write to temp dir, rename, then update meta.json; onboarding also sets master), then the draft restarts from it with an empty log. Same hash as latest → no new version (no extra extract_master run). Request carries an idempotency key; a double click publishes once. Open annotations carry over if their target id still exists, else `outdated`; never deleted.
Invariants (tested): no lost edits, no silent AI changes, no duplicate versions, deterministic render (`.tex`/`.txt` identical for same JSON; PDF with `SOURCE_DATE_EPOCH`), every revert auditable.
Alternatives: version per accept (rejected in DEC-012).

### DEC-018 One résumé schema for master, drafts and tailored
Reasoned by: human (2026-10-12; agent critique accepted: local ids + `source`)
Decision: extend `data/jobs/<id>/resume.json` (render.py shape) with `schema_version`, résumé-local stable ids on sections/entries/bullets, and optional `source` = master.yaml bullet/entry id. QA `bullet_fidelity` + consistency checks run only on bullets with `source`, only for tailored résumés. Annotations and history stay outside the schema (DEC-015/016). Old files migrate on read (no `schema_version` → v1, ids assigned).
Why: one schema, one renderer; uploaded/hand-edited bullets aren't in master.yaml, so they can't be keyed by master ids.
Alternatives: separate editor schema (two renderers, drift); master ids only (breaks for uploads/edits).
Amended 2026-10-12 (human, PR #171): stricter provenance. In a v1 job-dir résumé every bullet needs a `source` that resolves to a master.yaml bullet and passes the `bullet_fidelity` text check; the only unsourced exception is a bullet explicitly marked `origin: "user"`. A missing `source` is never read as user-written: unsourced without `origin: "user"` = hard `bullet_fidelity` fail. User-written ≠ fact-verified: the QA detail lists those bullets as "user-written, unverified" (render output unchanged). The AI never sets `origin`: the prepare runner strips it from the AI's résumé and fails the attempt (`careeros.match.strip_ai_origin`; a reuse/tweak base's own marks are kept), and the apply gate re-runs `bullet_fidelity` in code (`careeros.qa.bullet_provenance`) instead of trusting `prepare.json`. REQ-113 `tweak_cap` counts user-origin bullets toward the 3. Pre-v1 files keep their rules (every bullet a master id; `origin` ignored). Why: AI claims must trace to verified experience; number/tool audits can't catch fabricated achievements. Limit: a hand-edited file can still forge `origin`; tamper-proof authorship needs the DEC-019 import guard and DEC-020 `changes.jsonl` authors (TASK-028..030, TASK-032).
Amended 2026-10-12 (TASK-028): a draft write (`PUT .../draft`) carries `author: user|ai`; only `user` may add or move `origin: "user"` (the only allowed value). An `ai` write may keep a mark the previous draft held on the same bullet id and text, otherwise it is refused (422) and nothing is written. Still not tamper-proof until TASK-029 logs authors.
Amended 2026-10-12 (TASK-032; Reasoned by: agent, pending human review): the import guard (DEC-019) is the only path that sets `origin: "user"` on uploaded bullets: `careeros.resume_import.save` overwrites any `origin` in the import run's JSON and marks every bullet `user` only after each bullet and field is found (whitespace-normalised) in v1 `text.txt`; the v2 changes log those bullets author `user`.

### DEC-019 extract-master is the single import step, guarded
Reasoned by: human (2026-10-12; agent critique accepted: verbatim guard, all uploads)
Decision: every upload (master, variant, other) → existing text extraction (DEC-001) → one `extract-master` headless run producing `resume.json` (DEC-018) and, for the master, the pending master.yaml proposal. Deterministic guard: every bullet must appear verbatim (whitespace-normalised) in the upload's `text.txt` and the JSON must validate; fail → import marked failed, Action Item, original kept, no guessed résumé shown. Original file stays v1 read-only.
Why: one import pipeline; import must never invent content.
Alternatives: separate converter skill (second pipeline); trust the model (fabrication risk).
Consequences: one AI run per upload = visible wait during onboarding (DEC-011 cost, accepted).

### DEC-020 Published résumé versions store JSON only; outputs rendered on demand
Reasoned by: human (2026-10-12; outside review of TASK-031 on storage, agent pushed back on content-addressing and retention)
Decision: a published version is `resume.json` (DEC-018) + `changes.jsonl` (authors, moved from the draft, not copied). Text, ATS, `.tex` and PDF are derived on demand through one store helper; only the latest version's PDF is cached (`cache/`, keyed by hash(resume.json) + renderer version, disposable). v1 keeps the original upload and its extracted `text.txt` (import guard source, DEC-019). Unchanged hash = no new version; published versions are never deleted.
Why: measured per version ~10 KB JSON vs ~65 KB of derivable text/ATS/.tex/PDF; storage grows by the source only.
Alternatives: store all outputs per version (~7x storage); content-addressed blobs (saves only on non-adjacent identical versions, adds indirection); retention policy (deletes history, not needed at ~10 KB/version).
Consequences: an old version re-rendered after a template change looks new, not as published; PDFs actually sent to employers live in the job folder, unaffected. Readers of `text.txt`/`ats.json` for v2+ go through the helper.
