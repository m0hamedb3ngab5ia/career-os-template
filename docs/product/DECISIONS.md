# Decisions (product)
Repo-wide stable decisions: `.agent/DECISIONS.md`. This file: DEC entries from /product stages.

### DEC-001 Text extraction: pypdf + stdlib docx
Decision: PDF via `pypdf` (move from test extras to core deps); DOCX via stdlib `zipfile` + `xml.etree` on `word/document.xml`; txt/md read as UTF-8. Same extractor feeds ATS view (REQ-098) and match (REQ-111).
Reason: pypdf pure-Python, already used in tests; DOCX text is one XML file.
Alternatives: pdfminer.six (heavier), python-docx (dep for one file read), LLM extraction (non-deterministic).
Consequences: scanned/image PDFs → "no text found" warning, match 0. No OCR.

### DEC-002 Injection scan at Store.save_posting, flags in flags.json
Decision: `careeros.untrusted.scan(text, html)` runs inside `Store.save_posting` (single path for scout, Check a job, import). Patterns: instruction phrases (`ignore|disregard (all )?(previous|prior|above)`, `system prompt`, `you are now`, `as an AI`, `new instructions`), zero-width/bidi chars (U+200B-200F, 202A-202E, 2060-2064, FEFF), CSS-hidden or white/transparent text and `font-size:0` in raw HTML, tool/command names (`Bash`, `WebFetch`, `curl `, `mcp__`, `careeros `), mailto/emails inside instruction sentences. Hit → `flags.json` + Action Item. Patterns in code, extendable via `config/pipeline.yaml: injection.extra_patterns`.
Reason: one choke point; deterministic; cheap.
Alternatives: LLM classifier (costs a run per job, injectable itself).
Consequences: false positives cost one "I checked it" click.

### DEC-003 Match score formula
Decision: `match = 100 * (0.7*req_cov + 0.2*pref_cov + 0.1*title_cov)`, weights renormalised over non-empty groups. Skills = `score.json` required_skills / preferred_skills (one LLM score per job, then deterministic); title terms = posting title tokens minus stopwords. Term hit = `qa._term_in_text` with qa's variants (moved to shared `careeros.terms`). Résumé text = `extract` output (REQ-098).
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
Decision: layout in ARCHITECTURE.md delta "Storage layout"; `rid` = server-generated slug + 4 hex; tailored/tweaked outputs saved as `type: tailored` résumés with `category` (score category) so later jobs reuse them.
Reason: profile/ already gitignored and `--link`-able to the private repo; résumés are profile data.
Consequences: `careeros prune` never touches profile/resumes.

### DEC-009 Minimal UI: only what an approved REQ needs
Decision: IA + UX are the minimum that meets approved REQs/UCs/FLOWs, nothing more. Every screen, section, control and dialog cites a REQ/UC/FLOW in IA.md; anything in the current UI without one is a removal candidate (IA.md "Trim list"), removed before or alongside frontend TASKs, never extended. Visual/interaction quality follows Vercel Web Interface Guidelines (`web-design-guidelines` skill audit per frontend PR).
Reason: current UI grew well beyond the requirements (user, 2026-10-04); every extra surface costs build, test and review.
Alternatives: keep current UI and add delta on top (more slop); full redesign now (unscoped).
Consequences: frontend TASK-013..015 start with a trim pass; new UI needs a REQ first (`/product change`). Not implemented yet: recorded before development.
