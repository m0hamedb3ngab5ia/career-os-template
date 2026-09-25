# Vendored: ResumeSkills (reference material only)

- Source: https://github.com/Paramchoudhary/ResumeSkills
- Commit: `74ae19e` (the five files below are copied verbatim, unmodified)
- License: MIT, see [`LICENSE`](LICENSE) (Copyright (c) 2026 Resume Skills)

| File | Upstream path |
|---|---|
| `resume-bullet-writer/SKILL.md` | `skills/resume-bullet-writer/SKILL.md` |
| `tech-resume-optimizer/SKILL.md` | `skills/tech-resume-optimizer/SKILL.md` |
| `resume-quantifier/SKILL.md` | `skills/resume-quantifier/SKILL.md` |
| `resume-tailor/SKILL.md` | `skills/resume-tailor/SKILL.md` |
| `resume-ats-optimizer/SKILL.md` | `skills/resume-ats-optimizer/SKILL.md` |

## How career-os uses these files

These files are reference material read by `.claude/skills/_shared/resume_writing_rules.md`. They are
NOT loaded as skills: they live here, not under `.claude/skills/`, so Claude Code never auto-triggers them.

Do not move them into `.claude/skills/`. Parts of them conflict with career-os invariants (`CLAUDE.md`,
`.claude/skills/_shared/evidence_rules.md`). In particular, their advice to estimate numbers ("conservative
estimates", ranges, "if you think it was 60%, say 50%") is replaced by the OVERRIDE section of
`resume_writing_rules.md`: never estimate or invent a number; ask the candidate through
`profile/master.yaml: metric_questions`. Where the two disagree, `resume_writing_rules.md` wins.

To update: copy the same five files from a newer upstream commit verbatim, update the commit above, and
re-check `resume_writing_rules.md` against them.
