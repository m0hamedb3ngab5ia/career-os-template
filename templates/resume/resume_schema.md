# resume.json schema

`tailor-resume` writes `data/jobs/<job_id>/resume.json`. `templates/resume/render.py` turns it into
`resume.tex` (+ `resume.pdf` when a LaTeX engine exists) and `resume.txt`. QA (`qa-review`) reads the
same file to trace every bullet back to `profile/master.yaml` by `id`.

Rules:

- Every bullet `id` must exist in `profile/master.yaml`. Text may be a verbatim bullet or one of its
  `variants`; numbers are frozen.
- No placeholder bullets (`placeholder: true` in master, or text containing `[FILL IN` / `[OPEN:`).
- Text is plain: no LaTeX, no Markdown, with one exception: bullet `text` and `summary` may carry
  `**bold**` spans copied verbatim from `profile/master.yaml` (see "Bold markup" below). `render.py` escapes
  `& % $ # _ { } ~ ^ \`.
- Dates are display strings already formatted as `Mon YYYY` (QA soft rule `date_format`).
- Section order is decided by `sections[].order`; QA expects `experience, projects, education, skills`
  (summary optional, always first when present).

## Shape

```json
{
  "identity": {
    "name": "Alex Example",
    "email": "alex@example.com",
    "phone": "555-010-0199",
    "location": "Springfield, NY",
    "linkedin": "https://linkedin.com/in/alex-example",
    "github": "https://github.com/alex-example",
    "website": null
  },
  "summary": "string or null",
  "sections": [
    {"type": "experience", "order": 1},
    {"type": "projects",   "order": 2},
    {"type": "education",  "order": 3},
    {"type": "skills",     "order": 4}
  ],
  "experience": [
    {
      "id": "initech_intern",
      "company": "Initech",
      "title": "Data Engineering Intern",
      "team": "Reporting",
      "location": "Boston, MA",
      "start": "Jun 2025",
      "end": "Aug 2025",
      "bullets": [{"id": "initech_intern.1", "text": "..."}]
    }
  ],
  "projects": [
    {
      "id": "widgetizer",
      "name": "Widgetizer",
      "date": "Nov 2025",
      "stack": ["Swift", "SwiftUI", "Supabase"],
      "link": null,
      "bullets": [{"id": "widgetizer.1", "text": "..."}]
    }
  ],
  "education": [
    {
      "id": "state_u",
      "school": "Springfield State University",
      "degree": "Bachelor of Science, Computer Science",
      "gpa": "3.6",
      "location": "Springfield, NY",
      "start": "Aug 2022",
      "end": "May 2026",
      "coursework": ["Databases", "Machine Learning"],
      "activities": ["ACM Chapter Treasurer"]
    }
  ],
  "skills": {
    "programming": ["Python", "SQL", "Swift"],
    "frameworks": ["FastAPI", "React"],
    "tools": ["Git", "Airflow"],
    "concepts": ["ETL Pipelines", "REST APIs"]
  },
  "meta": {
    "job_id": "a1b2c3d4e5f6",
    "category": "swe_backend",
    "resume_version": "swe_backend-v1",
    "template": "default",
    "keyword_mirror": {"posting term": "profile term used"}
  }
}
```

## Field notes

| Field | Required | Notes |
|---|---|---|
| `identity.*` | name, email, phone, location | `website`, `linkedin`, `github` may be null; the header omits them. |
| `summary` | no | 2 to 3 sentences from `summary_variants`, or null. |
| `sections` | yes | Unknown `type` values are ignored. Missing sections are skipped. |
| `experience[].team` | no | Rendered after the title: "Title, Team". |
| `experience[].end` | yes | Use `Present` for current roles. |
| `projects[].link` | no | Rendered as a hyperlink on the project name. |
| `education[].location` | no | |
| `skill_groups` | no | `[{label, items}]` copied in order from `profile.skill_groups`; when present it replaces `skills`. Empty groups are omitted. |
| `skills_heading` | no | Section heading for skills (default `Skills`; from `profile.skills_heading`). |
| `skills.*` | no | Empty lists omit the line. Every term must exist in `profile.skills` or a cited bullet (QA `no_new_tools`). |
| `meta.template` | no | Overrides the template name (default: `categories.yaml[category].resume_template`, else `default`). |
| `meta.resume_version` | yes | Goes to the tracker `ResumeVersion` column. |
| `meta.keyword_mirror` | no | Posting term to profile phrasing map; QA uses it to check `keyword_coverage_min`. |

## Bold markup

The candidate bolds tech names and metrics in `profile/master.yaml` bullet `text` / `variants` (and
`summary_variants`) with `**...**`:

```yaml
text: Wrote **12 Airflow DAGs** in **Python** moving SQL reports into a warehouse, cutting manual prep by **5 hours per week**
```

- tailor-resume copies the text **with** its markers into `resume.json`; `render.py` writes `\textbf{12 Airflow
  DAGs}` in `resume.tex` (the inner text is LaTeX-escaped; no `*` reaches LaTeX) and the plain sentence in
  `resume.txt`, which is what ATS parsers and QA read.
- YAML: a value that starts with `**` must be quoted (`text: "**Python** scripts ..."`); unquoted, YAML reads
  the leading `*` as an alias and `master.yaml` stops parsing.
- Rules (`src/careeros/markup.py: validate_bold`): markers in pairs, no empty span (`****`), no space just inside
  a marker, no `***` / nesting. A single `*` is ordinary text. `**` in any other field (titles, skills, dates) is
  an error. `render.py` exits 1 on any violation and writes nothing; `careeros doctor` FAILs on invalid markup in
  master.yaml.
- QA compares bullet text with the markers stripped (`strip_bold`), so bold never changes a verdict. Hard check
  `bold_markup` re-validates resume.json and fails if resume.txt contains `**`.
- Cover letters, answers and outreach never carry the markers: `no_markdown_bold` hard-fails `**` in answers and
  outreach and a stray `**` in the letter; balanced bold in the letter body is the soft `cover_letter_bold`.

## Plain-text render order (`resume.txt`)

Header, Summary (if any), then sections in `sections[].order`. Each entry is one line for the
heading, one line for the subtitle, then bullets prefixed with `- `. This is what ATS parsers see;
QA's `contact_intact` check runs on this file and on PDF text extraction.
