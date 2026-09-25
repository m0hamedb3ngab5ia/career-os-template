# Voice guide — how the candidate writes

STATUS: no samples yet. Add 2–5 self-written samples to `profile/voice/samples/` and run `/learn-voice`.
Writer skills read this file + every sample before drafting. Until real samples exist, drafts lean on
the rules below and QA flags them `voice_unverified`.

## Letter settings (EDIT)

Writer skills read these lines; keep the `- Label:` shape.

- Greeting: "Hi <Team> team," when a real team name is known, else "Hi <Company> team,"
- Sign-off: "<first name from profile/master.yaml identity.name>"
- Length: config/qa.yaml cover_letter.min_words to cover_letter.max_words (QA enforces it)
- Close variants:
  - "Happy to walk through the code."
  - "Would like to talk."
  - "Glad to go deeper on any of this."

## Rules (EDIT freely)

- First person, direct. "I built X because Y." Not "X was built."
- Short sentences. One idea each. Paragraphs 2–4 sentences.
- Lead with the concrete thing, then why it matters to them.
- Contractions fine (I'm, it's, didn't).
- Numbers over adjectives. "2 million events per day" beats "high-volume".
- No throat-clearing openers ("I am writing to…", "I'm excited to…").
- No praise of the company beyond one specific, sourced fact.
- Close with a plain ask, rotated from `Close variants` above.
- Max 2 em-dashes per document. Prefer periods or commas.
- Never use words on `config/qa.yaml: banned_phrases`.

## Cover-letter skeleton (structure only)

1. **Hook** (1–2 sentences): the one thing about this role/team that connects to something the candidate actually did. Cite a posting/company fact.
2. **Proof A** (3–4 sentences): strongest matching experience for requirement #1. Use bullet ids.
3. **Proof B** (2–3 sentences): requirement #2 or the "why this domain" angle from `narratives`.
4. **Close** (1–2 sentences): one of the Close variants, then the Sign-off.

Greeting: see Letter settings. Never "Dear Hiring Manager".

## Samples

Put 2–5 files in `profile/voice/samples/` (cover letters, emails, essays the candidate wrote themselves — not AI-assisted).
Filename convention: `YYYY-MM_<what>.md`. `/learn-voice` extracts patterns (sentence length distribution,
favorite transitions, openers/closers) into `## Learned` below.

## Learned
