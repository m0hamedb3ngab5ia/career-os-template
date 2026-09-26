# resume.json schema

`tailor-resume` writes `data/jobs/<job_id>/resume.json`. `templates/resume/render.py` turns it into
`resume.tex` (+ `resume.pdf` when a LaTeX engine exists) and `resume.txt`. QA (`qa-review`) reads the
same file to trace every bullet back to `profile/master.yaml` by `id`.

Rules:

- Every bullet `id` must exist in `profile/master.yaml`. Text may be a verbatim bullet or one of its
  `variants`; numbers are frozen.
- No placeholder bullets (`placeholder: true` in master, or text containing `[FILL IN` / `[OPEN:`).
- Text is plain: no LaTeX, no Markdown. `render.py` escapes `& % $ # _ { } ~ ^ \`.
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

## Plain-text render order (`resume.txt`)

Header, Summary (if any), then sections in `sections[].order`. Each entry is one line for the
heading, one line for the subtitle, then bullets prefixed with `- `. This is what ATS parsers see;
QA's `contact_intact` check runs on this file and on PDF text extraction.
