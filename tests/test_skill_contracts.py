"""Skill docs are code: every `careeros ...` subcommand, repo file path and targets.yaml key a SKILL.md
references must exist (a wrong instruction in a skill is a defect; see docs/CODE_REVIEW_PROMPT.md)."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pytest
import yaml
from conftest import EXAMPLE_REPO, ROOT

from careeros.cli import build_parser

pytestmark = pytest.mark.unit

SKILLS = sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))
DOCS = SKILLS + sorted((ROOT / ".claude" / "skills" / "_shared").glob("*.md")) + sorted(
    (ROOT / "src" / "careeros" / "apply").glob("*.md"))
# User-facing docs: every command and file they tell a new user to run or edit must exist too.
USER_DOCS = [ROOT / "README.md", ROOT / "docs" / "GETTING_STARTED.md"]
DOCS = DOCS + USER_DOCS
CLI_RE = re.compile(r"careeros((?: [a-z][a-z-]*)+)")
PATH_RE = re.compile(r"(?<![\w/.])((?:profile|config|templates|src/careeros)/[\w/.-]+\.(?:ya?ml|md|py|tex))")
TARGETS_KEY_RE = re.compile(r"targets\.yaml: ?([a-z_]+(?:\.[a-z_]+)+)")


def _ids(paths):
    return [str(p.relative_to(ROOT)) for p in paths]


def _subparsers(p: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for a in p._actions:
        if isinstance(a, argparse._SubParsersAction):
            return dict(a.choices)
    return {}


def _check_cli(words: list[str]) -> str | None:
    parser = build_parser()
    for i, w in enumerate(words):
        subs = _subparsers(parser)
        if not subs:
            return None  # reached a leaf command; the rest are positional args
        if w not in subs:
            return f"`careeros {' '.join(words[:i + 1])}`: unknown subcommand {w!r} (have {sorted(subs)})"
        parser = subs[w]
    return None if not _subparsers(parser) else f"`careeros {' '.join(words)}` needs a subcommand"


def test_skills_found():
    assert len(SKILLS) >= 8


@pytest.mark.parametrize("doc", DOCS, ids=_ids(DOCS))
def test_cli_references_exist(doc: Path):
    problems = []
    for m in CLI_RE.finditer(doc.read_text(encoding="utf-8")):
        words = m.group(1).split()
        if words and words[0] in ("careeros",):
            continue
        err = _check_cli(words)
        if err:
            problems.append(err)
    assert not problems, problems


@pytest.mark.parametrize("doc", DOCS, ids=_ids(DOCS))
def test_file_references_exist(doc: Path):
    missing = []
    for m in PATH_RE.finditer(doc.read_text(encoding="utf-8")):
        rel = m.group(1).rstrip(".")
        if "<" in rel or "*" in rel:
            continue
        # profile/ and config/ are personal and gitignored: the shipped examples must have the file
        base = EXAMPLE_REPO if rel.split("/")[0] in ("profile", "config") else ROOT
        if not (base / rel).exists():
            missing.append(rel)
    assert not missing, missing


@pytest.mark.parametrize("doc", DOCS, ids=_ids(DOCS))
def test_targets_keys_exist(doc: Path):
    targets = yaml.safe_load((EXAMPLE_REPO / "config" / "targets.yaml").read_text())
    missing = []
    for m in TARGETS_KEY_RE.finditer(doc.read_text(encoding="utf-8")):
        node = targets
        for part in m.group(1).split("."):
            if not isinstance(node, dict) or part not in node:
                missing.append(m.group(1))
                break
            node = node[part]
    assert not missing, missing


@pytest.mark.parametrize("skill", SKILLS, ids=_ids(SKILLS))
def test_frontmatter_name_matches_dir(skill: Path):
    text = skill.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    # Claude Code reads frontmatter line by line (descriptions may contain ": "), so do the same
    head = text.split("---", 2)[1]
    meta = dict(line.split(": ", 1) for line in head.strip().splitlines() if ": " in line)
    assert meta["name"] == skill.parent.name and meta.get("description")


def test_checker_catches_bad_references():
    assert _check_cli(["tracker", "applied-count"]) is None
    assert _check_cli(["tracker", "upsert"]) is None
    assert _check_cli(["job", "status"]) is None
    assert "unknown subcommand 'nope'" in _check_cli(["tracker", "nope"])
    assert "needs a subcommand" in _check_cli(["tracker"])


# --- prepare-job / write-cover-letter contracts ---------------------------------------------------

SKILL_DIR = ROOT / ".claude" / "skills"


def _skill(name: str) -> str:
    return (SKILL_DIR / name / "SKILL.md").read_text(encoding="utf-8")


COVER_RENDER_RE = re.compile(r"\.venv/bin/python templates/cover_letter/render\.py JOB/cover_letter\.md")


def test_prepare_job_renders_cover_letter_txt():
    """apply-job pastes cover_letter.txt; prepare-job must produce it (render.py) and list it."""
    text = _skill("prepare-job")
    assert COVER_RENDER_RE.search(text), "prepare-job must run templates/cover_letter/render.py JOB/cover_letter.md"
    files = re.search(r'"files": \[([^\]]*)\]', text).group(1)
    assert '"cover_letter.txt"' in files and '"resume.pdf"' in files


def _letter_required(posting: str) -> bool:
    text = _skill("prepare-job")
    req = re.search(r"\(regex `([^`]+)`\)", text)
    opt_out = re.search(r"\(opt-out regex `([^`]+)`\)", text)
    assert req and opt_out, "prepare-job must state the cover-letter-required and opt-out regexes"
    return bool(re.search(req.group(1), posting, re.I)) and not re.search(opt_out.group(1), posting, re.I)


@pytest.mark.parametrize("posting,required", [
    ("Please submit a cover letter with your application.", True),
    ("A cover letter is required.", True),
    ("Cover letter required.", True),
    ("Please include a short cover letter.", True),
    ("Cover letters are optional.", False),
    ("We build ledgers.", False),
    ("Do not include a cover letter.", False),
    ("Please note that a cover letter is optional.", False),
    ("No cover letter needed.", False),
    ("Please upload your resume; a cover letter is not required.", False),
])
def test_cover_letter_required_regex_both_word_orders(posting, required):
    assert _letter_required(posting) is required


def test_letter_skeleton_and_example_defer_to_letter_settings():
    skeleton = (ROOT / "templates" / "cover_letter" / "skeleton.md").read_text(encoding="utf-8")
    example = _skill("write-cover-letter").split("## 5.", 1)[1].split("## 6.", 1)[0]
    for text in (skeleton, example):
        assert not re.search(r"\b120\b.{0,10}\b250\b", text)
        assert "Hi <Team> team," not in text and "Hi <Company> team," not in text
    assert "Letter settings" in skeleton and "Happy to walk through the code." not in skeleton


def test_write_cover_letter_reads_length_and_voice_from_candidate_files():
    text = _skill("write-cover-letter")
    assert not re.search(r"\b120\s*[-–]\s*250\b", text), "length must come from config/qa.yaml, not a hardcode"
    assert "cover_letter.min_words" in text and "cover_letter.max_words" in text
    assert "close_variant" in text and "Dear Hiring Manager" in text
    assert "Hi <Company> team," not in text, "greeting format comes from the style guide"


def test_example_style_guide_declares_letter_settings():
    guide = (EXAMPLE_REPO / "profile" / "voice" / "style_guide.md").read_text(encoding="utf-8")
    for label in ("Greeting:", "Sign-off:", "Length:", "Close variants:"):
        assert re.search(rf"^- {re.escape(label)}", guide, re.M), label
    variants = re.search(r"^- Close variants:\n((?:  - .+\n)+)", guide, re.M)
    assert variants and len(variants.group(1).strip().splitlines()) >= 3


def test_tailor_resume_section_order_comes_from_config():
    text = _skill("tailor-resume")
    assert "resume.hard.section_order" in text
    assert "put `projects`\n   before `experience`" not in text and "projects` before `experience`" not in text


def test_tailor_resume_bullet_rule_matches_qa_fidelity():
    """QA bullet_fidelity accepts master text or a declared variant, optionally trimmed at the end; the
    skill must not promise more (e.g. free synonym swaps of the leading verb)."""
    rule = _skill("tailor-resume").split("1. Every bullet you output", 1)[1].split("\n2. ", 1)[0]
    assert "synonym" not in rule and "variants" in rule and "trailing" in rule



# --- apply-job contracts (submit safety, QA gate, override, answers.json) ----------------------------

def test_apply_job_gates_on_qa_review_pass_field():
    text = _skill("apply-job")
    assert "passed: true" not in text
    assert re.search(r"`qa\.json`[^\n]*`pass`", text) and "deterministic.pass" in text


def test_apply_job_persists_submit_before_clicking_and_refuses_reruns():
    text = _skill("apply-job")
    assert "ApplySession.already_submitted(job_dir)" in text
    click = text.index("one click on the submit control")
    assert 0 <= text.rfind("s.mark_submit_clicked(job_dir)", 0, click) < click


def test_apply_job_reads_override_via_cli_and_allows_tier_a_staging():
    text = _skill("apply-job")
    assert "careeros tracker show <job_id> --json" in text
    assert "needs_review" in text.split("## 1.", 1)[1].split("### 1b", 1)[0]
    assert "answers.json[" not in text


@pytest.mark.parametrize("skill", ["prepare-job", "apply-job"])
def test_fake_data_guard_runs_doctor_first(skill: str):
    """Both skills that produce or submit an application run `careeros doctor --quiet` before anything
    else and stop on a nonzero exit (untouched example data, missing claude CLI, broken YAML)."""
    text = (ROOT / ".claude" / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    body = text.split("---", 2)[2]
    first_step = body.index("## ")
    guard = body.find("careeros doctor --quiet")
    assert 0 <= guard < body.index("## ", first_step + 3), "doctor guard must come in the first section"
    assert "nonzero" in body[guard - 400: guard + 600].lower() or "non-zero" in body[guard - 400: guard + 600].lower()


def test_user_docs_exist_and_link():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert (ROOT / "docs" / "GETTING_STARTED.md").is_file()
    head = readme[: readme.index("## ", readme.index("## ") + 3)] if readme.count("## ") > 1 else readme
    assert "docs/GETTING_STARTED.md" in head, "README must point to the getting-started guide first"
    for section in ("## How it works", "## What you configure vs what's reusable", "## Reference"):
        assert section in readme, section
    assert readme.index("## Reference") > readme.index("## How it works")


# --- résumé-writing rules (_shared/resume_writing_rules.md, vendored ResumeSkills reference) ---------

RULES = SKILL_DIR / "_shared" / "resume_writing_rules.md"
VENDORED = ["resume-bullet-writer", "tech-resume-optimizer", "resume-quantifier", "resume-tailor",
            "resume-ats-optimizer"]


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    nxt = re.search(r"^#{1,3} ", text[start + len(heading):], re.M)
    return text[start: start + len(heading) + (nxt.start() if nxt else len(text))]


def test_resume_writing_rules_exist_and_are_referenced():
    assert RULES.is_file()
    for skill in ("tailor-resume", "qa-review"):
        assert ".claude/skills/_shared/resume_writing_rules.md" in _skill(skill), skill
    assert "evidence_rules.md" in RULES.read_text(encoding="utf-8")


def test_resume_writing_rules_power_verbs_avoid_banned_phrases():
    text = RULES.read_text(encoding="utf-8")
    verbs = [v.strip().lower() for line in _section(text, "## Power verbs").splitlines()
             if line.startswith("- **") for v in line.split(":**", 1)[1].split(",") if v.strip()]
    assert len(verbs) >= 30
    banned = [str(b).lower().rstrip(",") for b in
              yaml.safe_load((EXAMPLE_REPO / "config" / "qa.yaml").read_text())["banned_phrases"]]
    assert not [v for v in verbs if any(re.search(rf"(?<![a-z]){re.escape(b)}(?![a-z])", v) for b in banned)]
    assert "config/qa.yaml" in _section(text, "## Power verbs")


def test_resume_writing_rules_weak_openers_match_qa_config():
    text = RULES.read_text(encoding="utf-8")
    listed = re.findall(r"^- `([a-z ]+)`", _section(text, "## Weak openers"), re.M)
    soft = yaml.safe_load((EXAMPLE_REPO / "config" / "qa.yaml").read_text())["resume"]["soft"]
    assert listed and set(listed) == set(soft["weak_openers"])


def test_resume_writing_rules_override_forbids_estimates():
    text = RULES.read_text(encoding="utf-8")
    override = _section(text, "## OVERRIDE")
    assert text.index("## OVERRIDE") < text.index("## Formulas"), "the override comes before any vendored advice"
    for needle in ("never estimate", "metric_questions", "bullet_id", "question", "`~`", "estimate: true",
                   "soft target"):
        assert needle in override.lower() if needle.islower() else needle in override, needle
    assert "contributed to" in text and "member of" in text  # ownership honesty


def test_vendored_resumeskills_are_reference_only():
    base = ROOT / "third_party" / "resumeskills"
    readme = (base / "README.md").read_text(encoding="utf-8")
    assert "https://github.com/Paramchoudhary/ResumeSkills" in readme and "74ae19e" in readme and "MIT" in readme
    assert "NOT loaded as skills" in readme
    assert (base / "LICENSE").is_file()
    for name in VENDORED:
        assert (base / name / "SKILL.md").is_file(), name
        assert not (SKILL_DIR / name).exists(), f"{name} must not sit under .claude/skills (it would auto-trigger)"
        assert f"third_party/resumeskills/{name}/SKILL.md" in RULES.read_text(encoding="utf-8")


def test_tailor_resume_prefers_resume_default_and_qa_review_scores_bullet_strength():
    tailor = _skill("tailor-resume")
    assert "resume_default: true" in tailor and "weak: true" in tailor
    qa = _skill("qa-review")
    row = next(ln for ln in qa.splitlines() if ln.startswith("| bullet_strength |"))
    for part in ("action verb", "technical", "scale", "tech"):
        assert part in row, part
    assert "bullet_shape" in qa


def test_apply_job_scam_gate_runs_the_safety_cli():
    """§1b calls the code gate (not a prose-only procedure) before filling and again on visible fields,
    and auto-submit also needs the allowlist verdict."""
    gate = _skill("apply-job").split("### 1b", 1)[1].split("\n## ", 1)[0]
    assert "careeros safety check <job_id>" in gate
    assert "careeros safety fields <job_id>" in gate
    assert "auto_submit_allowed" in _skill("apply-job")
    assert "no code yet" not in gate


def test_score_job_uses_three_verdicts_and_reason_codes():
    text = _skill("score-job")
    assert "careeros safety check" in text and "careeros safety signal" in text
    for word in ("Pass", "Review", "Block", "SCAM_", "GHOST_", "COMPANY_"):
        assert word in text, word
    # unknown is not suspicious: the made-up-company rubric has three risk levels and a two-signal minimum
    assert "Sparse information alone is not evidence of fraud" in text
    assert "--risk low" in text and "--risk medium" in text and "--risk high" in text


def test_apply_job_follows_safety_verdict():
    text = _skill("apply-job")
    assert "verdict" in text and "block" in text and "review" in text


# --- company policy (caps, cooldown with deadline exception, transparency) --------------------------

@pytest.mark.parametrize("skill", ["score-job", "prepare-job"])
def test_prepare_path_runs_company_gate_before_preparing(skill: str):
    text = _skill(skill)
    assert "careeros company gate" in text
    for reason in ("company_cap", "cooldown"):
        assert reason in text, reason


def test_score_job_gate_comes_before_the_final_decision_is_recorded():
    text = _skill("score-job")
    assert text.index("careeros company gate") > text.index("## 7. Decision")
    assert "careeros company requeue" in text


def test_prepare_job_gates_before_tailoring():
    text = _skill("prepare-job")
    assert text.index("careeros company gate") < text.index("## Step 2: resume")


def test_apply_job_uses_company_gate_not_manual_lookups():
    pre = _skill("apply-job").split("## 1.", 1)[1].split("### 1b", 1)[0]
    assert "careeros company gate <job_id>" in pre
    assert 'applied-count "<company>"' not in pre, "company cap now comes from `careeros company gate`"
    assert "--status rejected" not in pre, "cooldown now comes from `careeros company gate`"
    assert "applied-count --days 1" in pre, "the daily cap stays"


@pytest.mark.parametrize("skill", ["prepare-job", "apply-job"])
def test_urgent_jobs_go_first(skill: str):
    text = _skill(skill)
    assert "careeros jobs list --status queued --order urgent" in text
    assert "action_note" in text


def test_inbox_sync_adds_transparency_note():
    text = _skill("inbox-sync")
    assert "careeros company active" in text and "--exclude <job_id>" in text
    assert "mention these to the recruiter" in text


def test_prepare_job_batch_scores_everything_before_preparing():
    text = _skill("prepare-job")
    batch = text.split("Batches", 1)[1].split("## Step 2", 1)[0]
    assert "Phase 1" in batch and "Phase 2" in batch
    assert batch.index("score-job") < batch.index("Phase 2"), "score every found job before preparing any"
    assert "careeros jobs list --status found --status scored --order urgent" in batch
    assert "careeros company gate" in batch.split("Phase 2", 1)[1], "gate again right before each prepare"


def test_prepare_job_gate_skip_note_starts_with_reason_and_deferrals_reach_the_gate():
    text = _skill("prepare-job")
    step1 = text.split("## Step 1: score", 1)[1].split("## Step 1b", 1)[0]
    assert "company_cap" in step1 and "Step 1b" in step1, "a deferred score-job skip is re-decided by the gate"
    step1b = text.split("## Step 1b", 1)[1].split("## Step 2", 1)[0]
    assert '--note "<gate.reason>: <gate.detail>"' in step1b


def test_apply_job_gate_exit_3_skips_permanent_reasons():
    pre = _skill("apply-job").split("## 1.", 1)[1].split("### 1b", 1)[0]
    row = next(line for line in pre.splitlines() if "careeros company gate <job_id>" in line)
    assert "status unchanged" in row and "`company_cap` / `cooldown`" in row
    assert 'careeros job status <job_id> skipped --note "company <reason>: <detail>"' in row
    for reason in ("closed", "not_similar", "already_applied"):
        assert reason in row, reason


def test_draft_outreach_opens_one_action_item_per_job_for_manual_contacts():
    """`action add --dedupe` keys on job + type, so per-contact items would drop all but the first."""
    t = (ROOT / ".claude" / "skills" / "draft-outreach" / "SKILL.md").read_text(encoding="utf-8")
    assert "one Action Item per contact" not in t
    assert "name every manual contact in that item" not in t
    assert "action_text" in t and "--dedupe" in t
