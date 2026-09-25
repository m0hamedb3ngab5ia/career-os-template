"""Applier: Chrome-driven form filling.

The browser work happens inside Claude Code via the Claude in Chrome tools, following
`.claude/skills/apply-job/SKILL.md` and the per-ATS flows in `adapters.md`. This package holds the
pure-Python helpers the skill calls:

- `questions`: map a form question to `profile/standard_answers.yaml`, classify the rest.
- `session`: `ApplySession` record written to `data/jobs/<id>/apply_session.json` + `log.md`.
- `detection.yaml`: registry of companies/domains where bot detection was hit.
"""
from careeros.apply.questions import classify_question, match_standard_answer, select_eeo_option
from careeros.apply.session import ApplySession

__all__ = ["ApplySession", "classify_question", "match_standard_answer", "select_eeo_option"]
