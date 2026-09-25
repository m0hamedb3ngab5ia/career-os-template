---
name: learn-voice
description: Extract the candidate's writing style from profile/voice/samples/* (self-written cover letters, emails, essays) and write measurable patterns plus 5 verbatim anchor sentences into the "## Learned" section of profile/voice/style_guide.md.
---

# learn-voice

`$ARGUMENTS` = optional path to the voice dir (default `profile/voice`). Call it `VOICE`.

## 1. Read samples

List `VOICE/samples/*` (accept .md, .txt, .eml; ignore hidden files). Read every file fully.
If there are 0 samples: do not modify `## Learned`; print
`RESULT: {"skill":"learn-voice","voice_samples_count":0,"error":"no samples in profile/voice/samples/"}` and stop.

Strip YAML frontmatter, email headers (`From:`, `Subject:`, quoted `>` lines), signatures repeated
across files, and any text that is obviously quoted from someone else.

## 2. Measure (compute, do not guess)

Split into sentences (`.`, `!`, `?` followed by space/newline). Split paragraphs on blank lines. Report:

- `sentences_total`, `avg_sentence_words` (1 decimal), `median_sentence_words`, `pct_sentences_under_12_words`,
  `longest_sentence_words`.
- `avg_paragraph_sentences`.
- `contractions_per_100_words` (count `'m|'s|'re|'ve|'ll|'d|n't`).
- `first_person_per_100_words` (`I`, `I'm`, `I've`, `my`).
- Punctuation habits: em-dashes per doc, semicolons per doc, colons per doc, parentheses per doc,
  exclamation marks per doc, use of Oxford comma (yes/no/mixed), lists as sentences vs bullets.
- Openers: the first sentence of each sample verbatim. Note the pattern (fact-first? name-first? question?).
- Closers: the last non-signature sentence of each sample verbatim. Note the ask pattern and sign-off form.
- Transitions: every sentence-initial word/phrase that appears >= 2 times across samples
  (`So`, `Also`, `Then`, `That said`, `In practice`, ...), with counts.
- Vocabulary they actually use: 15-25 content words/phrases that recur (verbs like "built", "shipped",
  "wired up"; nouns; hedges like "roughly", "about"). Exclude stopwords and company names.
- Things they never do (only claim what the samples show): e.g. no rhetorical questions, no "passionate",
  no bullet lists in letters, no exclamation marks, never opens with "I am writing".
- Any `config/qa.yaml: banned_phrases` they DO use in samples -> list under `conflicts` (the ban still wins).

## 3. Pick 5 anchor sentences

Choose 5 sentences, verbatim, from different samples where possible, that best represent: (1) how they
open, (2) how they state a result with a number, (3) how they explain a why, (4) a transition mid-letter,
(5) how they close/ask. Each with its source filename.

## 4. Write into `VOICE/style_guide.md`

Replace everything from the line `## Learned` to end-of-file (or to the next `## ` heading if one
follows) with:

```markdown
## Learned

voice_samples_count: <n>
learned_at: <YYYY-MM-DD>
samples: [<filenames>]

### Metrics
- avg sentence length: <x> words (median <y>; <p>% under 12 words; longest <z>)
- paragraphs: ~<n> sentences each
- contractions: <x> per 100 words; first person: <y> per 100 words
- punctuation: em-dashes <a>/doc, semicolons <b>/doc, colons <c>/doc, parentheses <d>/doc, exclamations <e>/doc, Oxford comma: <yes|no|mixed>

### Openers
- <pattern description>
- verbatim: "<opener 1>" (<file>) ...

### Closers
- <pattern>; sign-off: "<form>"
- verbatim: ...

### Transitions they use
- <word> (<count>), ...

### Vocabulary they actually use
<comma-separated list>

### Things they never do
- ...

### Conflicts with config/qa.yaml
- <phrase> appears in <file>; still banned in generated text.

### Anchor sentences (verbatim)
1. "<sentence>" (<file>)
2. ...
5. ...
```

Do not edit the `## Rules` or skeleton sections. Keep the file's `STATUS:` line but change it to
`STATUS: learned from <n> samples on <date>. Re-run /learn-voice after adding samples.`

## 5. RESULT

`RESULT: {"skill":"learn-voice","voice_samples_count":3,"avg_sentence_words":13.4,"anchors":5,"conflicts":["leverage"],"file":"profile/voice/style_guide.md"}`
