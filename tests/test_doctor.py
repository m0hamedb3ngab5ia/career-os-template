"""Unit tests for careeros.doctor: the setup checklist (fresh example copy fails, filled-in root passes)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from conftest import EXAMPLE_REPO, personalize

from careeros.doctor import (
    FAIL,
    PASS,
    WARN,
    Check,
    exit_code,
    format_report,
    run_doctor,
    schema_problems,
)

pytestmark = pytest.mark.unit

ALL_TOOLS = {"claude", "tectonic", "pdflatex", "gh", "codex"}


def which_from(present: set[str]):
    return lambda name: f"/fake/bin/{name}" if name in present else None


def fresh(tmp_path: Path) -> Path:
    """What `careeros init` produces: examples/{config,profile} copied verbatim."""
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copytree(EXAMPLE_REPO / "config", root / "config")
    shutil.copytree(EXAMPLE_REPO / "profile", root / "profile")
    return root


def filled(tmp_path: Path) -> Path:
    return personalize(fresh(tmp_path))


def doctor(root: Path, tools: set[str] = ALL_TOOLS, env: dict[str, str] | None = None) -> list[Check]:
    # env pinned: this suite may itself run inside Claude Code (CLAUDECODE=1)
    return run_doctor(root, which=which_from(tools), examples=EXAMPLE_REPO, env=env or {})


def details(checks: list[Check], level: str) -> list[str]:
    return [f"{c.name}: {c.detail}" for c in checks if c.level == level]


def text_of(checks: list[Check], level: str) -> str:
    return "\n".join(details(checks, level))


# --- setup ------------------------------------------------------------------------------------

def test_missing_personal_dirs_fail(tmp_path: Path):
    checks = doctor(tmp_path)
    fails = text_of(checks, FAIL)
    assert "profile/" in fails and "config/" in fails and "careeros init" in fails
    assert exit_code(checks) == 1


def test_invalid_yaml_fails_with_file_name(tmp_path: Path):
    root = filled(tmp_path)
    (root / "config" / "targets.yaml").write_text("candidate: [unclosed\n")
    checks = doctor(root)
    assert "config/targets.yaml" in text_of(checks, FAIL)
    assert exit_code(checks) == 1


def test_missing_required_key_fails(tmp_path: Path):
    root = filled(tmp_path)
    t = yaml.safe_load((root / "config" / "targets.yaml").read_text())
    del t["tiers"]
    (root / "config" / "targets.yaml").write_text(yaml.safe_dump(t))
    assert "config/targets.yaml: tiers" in text_of(doctor(root), FAIL)


def test_schema_problems_empty_for_examples():
    load = lambda p: yaml.safe_load(p.read_text())  # noqa: E731
    cfg = {n: load(EXAMPLE_REPO / "config" / f"{n}.yaml") for n in ("targets", "categories", "companies", "qa", "pipeline")}
    prof = {n: load(EXAMPLE_REPO / "profile" / f"{n}.yaml") for n in ("master", "standard_answers", "confidential_terms")}
    assert schema_problems(cfg, prof) == []


def test_schema_problems_names_missing_standard_answer_key():
    load = lambda p: yaml.safe_load(p.read_text())  # noqa: E731
    cfg = {n: load(EXAMPLE_REPO / "config" / f"{n}.yaml") for n in ("targets", "categories", "companies", "qa", "pipeline")}
    prof = {n: load(EXAMPLE_REPO / "profile" / f"{n}.yaml") for n in ("master", "standard_answers", "confidential_terms")}
    prof["standard_answers"]["answers"] = [a for a in prof["standard_answers"]["answers"] if a["key"] != "phone"]
    probs = schema_problems(cfg, prof)
    assert any("profile/standard_answers.yaml" in p and "phone" in p for p in probs), probs


# --- untouched example data = FAIL ------------------------------------------------------------

def test_fresh_example_copy_fails_on_identity(tmp_path: Path):
    checks = doctor(fresh(tmp_path))
    fails = text_of(checks, FAIL)
    for key in ("identity.name", "identity.email", "identity.phone", "identity.linkedin", "identity.github"):
        assert f"profile/master.yaml: {key}" in fails, key
    assert "Alex Example" in fails
    assert exit_code(checks) == 1


def test_fresh_copy_fails_on_example_ids_and_standard_answers(tmp_path: Path):
    fails = text_of(doctor(fresh(tmp_path)), FAIL)
    assert "experience id 'acme'" in fails and "experience id 'initech_intern'" in fails
    assert "profile/standard_answers.yaml" in fails and "identical to the example" in fails


def test_example_dot_com_email_anywhere_fails(tmp_path: Path):
    root = filled(tmp_path)
    sa = yaml.safe_load((root / "profile" / "standard_answers.yaml").read_text())
    sa["answers"].append({"key": "email", "match": ["email"], "answer": "sam@example.com"})
    (root / "profile" / "standard_answers.yaml").write_text(yaml.safe_dump(sa))
    fails = text_of(doctor(root), FAIL)
    assert "profile/standard_answers.yaml" in fails and "sam@example.com" in fails


def test_single_example_identity_field_left_fails(tmp_path: Path):
    root = filled(tmp_path)
    m = yaml.safe_load((root / "profile" / "master.yaml").read_text())
    m["identity"]["github"] = "https://github.com/alex-example"
    (root / "profile" / "master.yaml").write_text(yaml.safe_dump(m))
    fails = details(doctor(root), FAIL)
    assert any("profile/master.yaml: identity.github" in f for f in fails), fails
    assert not any("identity.name" in f for f in fails)


def test_filled_in_root_passes(tmp_path: Path):
    checks = doctor(filled(tmp_path))
    assert details(checks, FAIL) == []
    assert exit_code(checks) == 0
    assert any(c.level == PASS and c.name == "example_data" for c in checks)


# --- INSERT / EDIT markers --------------------------------------------------------------------

def test_unchanged_insert_lines_warn_with_file_and_line(tmp_path: Path):
    root = filled(tmp_path)
    shutil.copy(EXAMPLE_REPO / "config" / "targets.yaml", root / "config" / "targets.yaml")
    warns = [d for d in details(doctor(root), WARN) if d.startswith("unchanged_placeholder")]
    assert warns and all("config/targets.yaml:" in w for w in warns), warns
    assert any("min_base_usd" in w for w in warns)


def test_edited_or_reviewed_insert_line_does_not_warn(tmp_path: Path):
    root = filled(tmp_path)
    src = (EXAMPLE_REPO / "config" / "targets.yaml").read_text()
    marked = [ln for ln in src.splitlines() if "# INSERT" in ln]
    # change every value (keep the comments) -> nothing unchanged
    out = src
    for ln in marked:
        out = out.replace(ln, ln.replace("# INSERT", "#changed INSERT", 1).replace(":", ": ", 1), 1)
    (root / "config" / "targets.yaml").write_text(out)
    assert not [d for d in details(doctor(root), WARN) if "config/targets.yaml" in d]


def test_legacy_edit_marker_also_warns(tmp_path: Path):
    root = filled(tmp_path)
    ex = tmp_path / "ex"
    shutil.copytree(EXAMPLE_REPO, ex)
    (ex / "config" / "targets.yaml").write_text((ex / "config" / "targets.yaml").read_text()
                                                + "legacy_key: 1   # EDIT\n")
    (root / "config" / "targets.yaml").write_text((root / "config" / "targets.yaml").read_text()
                                                  + "legacy_key: 1   # EDIT\n")
    checks = run_doctor(root, which=which_from(ALL_TOOLS), examples=ex)
    assert any("legacy_key" in d for d in details(checks, WARN))


# --- categories --------------------------------------------------------------------------------

def test_bullet_priority_unknown_id_fails(tmp_path: Path):
    root = filled(tmp_path)
    c = yaml.safe_load((root / "config" / "categories.yaml").read_text())
    c["swe_backend"]["bullet_priority"] = ["northwind", "ghost_job"]
    (root / "config" / "categories.yaml").write_text(yaml.safe_dump(c))
    fails = text_of(doctor(root), FAIL)
    assert "config/categories.yaml: swe_backend.bullet_priority" in fails and "ghost_job" in fails


def test_fresh_bullet_priority_matches_example_ids(tmp_path: Path):
    """On the untouched copy ids agree (acme is in both); the example_data check is what fails."""
    fails = text_of(doctor(fresh(tmp_path)), FAIL)
    assert "bullet_priority" not in fails


# --- tools ------------------------------------------------------------------------------------

def test_missing_claude_fails(tmp_path: Path):
    checks = doctor(filled(tmp_path), tools=ALL_TOOLS - {"claude"})
    assert "claude" in text_of(checks, FAIL)
    assert exit_code(checks) == 1


def test_missing_optional_tools_warn(tmp_path: Path):
    checks = doctor(filled(tmp_path), tools={"claude"})
    warns = text_of(checks, WARN)
    assert "tectonic" in warns and "pdflatex" in warns and "gh" in warns and "codex" in warns
    assert exit_code(checks) == 0


def test_pdflatex_alone_is_enough(tmp_path: Path):
    checks = doctor(filled(tmp_path), tools={"claude", "pdflatex", "gh", "codex"})
    assert not [c for c in checks if c.name == "latex" and c.level != PASS]


# --- voice ------------------------------------------------------------------------------------

def test_no_voice_samples_warns(tmp_path: Path):
    root = filled(tmp_path)
    for f in (root / "profile" / "voice" / "samples").iterdir():
        f.unlink()
    (root / "profile" / "voice" / "samples" / ".gitkeep").write_text("")
    assert "voice" in text_of(doctor(root), WARN)


def test_voice_sample_present_passes(tmp_path: Path):
    checks = doctor(filled(tmp_path))
    assert any(c.name == "voice_samples" and c.level == PASS for c in checks)


# --- report -----------------------------------------------------------------------------------

def test_format_report_full_and_quiet():
    checks = [Check(PASS, "setup", "ok"), Check(WARN, "voice_samples", "0 samples"), Check(FAIL, "example_data", "x")]
    full = format_report(checks)
    assert "PASS" in full and "WARN" in full and "FAIL" in full and "1 fail, 1 warn, 1 pass" in full
    quiet = format_report(checks, quiet=True)
    assert "FAIL" in quiet and "voice_samples" not in quiet and "setup" not in quiet
    assert format_report([Check(PASS, "setup", "ok")], quiet=True) == ""
    assert exit_code(checks) == 1 and exit_code(checks[:2]) == 0


def test_placeholder_warnings_are_one_line_per_file_with_line_and_key(tmp_path: Path):
    warns = [d for d in details(doctor(fresh(tmp_path)), WARN) if d.startswith("unchanged_placeholder")]
    files = [w.split(": ")[1] for w in warns]
    assert len(files) == len(set(files))  # grouped per file, not one line per placeholder
    sa = next(w for w in warns if "profile/standard_answers.yaml" in w)
    assert "phone.answer" in sa and "gender.answer" in sa  # repeated keys qualified by their entry
    assert any("config/targets.yaml" in w and "min_base_usd" in w for w in warns)



def test_missing_claude_cli_passes_when_running_inside_claude_code(tmp_path: Path):
    """prepare-job/apply-job run `careeros doctor --quiet` from inside Claude Code (Desktop, IDE, web),
    where the `claude` binary may not be on PATH; the skill running is proof enough."""
    checks = doctor(filled(tmp_path), tools=ALL_TOOLS - {"claude"}, env={"CLAUDECODE": "1"})
    assert "claude" not in text_of(checks, FAIL)
    assert any(c.name == "claude" and c.level == PASS for c in checks)


# --- résumé-writing keys (resume_default / weak / estimate, metric_questions, bullet_shape config) ---

def _examples_cfg_prof():
    load = lambda p: yaml.safe_load(p.read_text())  # noqa: E731
    cfg = {n: load(EXAMPLE_REPO / "config" / f"{n}.yaml") for n in ("targets", "categories", "companies", "qa", "pipeline")}
    prof = {n: load(EXAMPLE_REPO / "profile" / f"{n}.yaml") for n in ("master", "standard_answers", "confidential_terms")}
    return cfg, prof


def test_example_demonstrates_optional_bullet_keys_and_metric_questions():
    _, prof = _examples_cfg_prof()
    m = prof["master"]
    bullets = [b for e in m["experience"] + m["projects"] for b in e["bullets"]]
    assert any(b.get("resume_default") is True for b in bullets)
    assert m["metric_questions"] and all({"bullet_id", "question"} <= set(q) for q in m["metric_questions"])
    ids = {b["id"] for b in bullets}
    assert all(q["bullet_id"] in ids for q in m["metric_questions"])


def test_optional_bullet_keys_absent_is_fine():
    cfg, prof = _examples_cfg_prof()
    prof["master"].pop("metric_questions")
    for e in prof["master"]["experience"] + prof["master"]["projects"]:
        for b in e["bullets"]:
            for k in ("resume_default", "weak", "estimate"):
                b.pop(k, None)
    assert schema_problems(cfg, prof) == []


@pytest.mark.parametrize("key", ["resume_default", "weak", "estimate"])
def test_optional_bullet_flag_must_be_bool(key: str):
    cfg, prof = _examples_cfg_prof()
    prof["master"]["experience"][0]["bullets"][0][key] = "yes"
    assert any(f"acme.1.{key} must be true or false" in p for p in schema_problems(cfg, prof))
    prof["master"]["experience"][0]["bullets"][0][key] = False
    assert schema_problems(cfg, prof) == []


@pytest.mark.parametrize("mq", [
    "ask me later",
    [{"bullet_id": "acme.3"}],
    [{"question": "How many?"}],
    ["acme.3: how many?"],
])
def test_metric_questions_shape(mq):
    cfg, prof = _examples_cfg_prof()
    prof["master"]["metric_questions"] = mq
    assert any("profile/master.yaml: metric_questions" in p for p in schema_problems(cfg, prof))


def test_metric_questions_empty_or_null_is_fine():
    cfg, prof = _examples_cfg_prof()
    for v in ([], None):
        prof["master"]["metric_questions"] = v
        assert schema_problems(cfg, prof) == []


def test_qa_yaml_bullet_shape_keys_optional_but_typed():
    cfg, prof = _examples_cfg_prof()
    soft = cfg["qa"]["resume"]["soft"]
    soft.pop("bullet_max_words"), soft.pop("weak_openers"), soft.pop("scale_words", None)
    assert schema_problems(cfg, prof) == []  # personal configs from before this key existed still pass
    soft["bullet_max_words"] = "thirty"
    soft["weak_openers"] = "helped"
    probs = schema_problems(cfg, prof)
    assert any("config/qa.yaml: resume.soft.bullet_max_words" in p for p in probs)
    assert any("config/qa.yaml: resume.soft.weak_openers" in p for p in probs)


def test_open_metric_questions_warn_with_count(tmp_path: Path):
    root = filled(tmp_path)
    m = yaml.safe_load((root / "profile" / "master.yaml").read_text())
    m["metric_questions"] = [{"bullet_id": "northwind.3", "question": "How much faster did deploys get?"},
                             {"bullet_id": "contoso_intern.2", "question": "How many reports use the lineage?"}]
    (root / "profile" / "master.yaml").write_text(yaml.safe_dump(m))
    checks = doctor(root)
    assert "metric_questions: 2 metric questions open in profile/master.yaml" in details(checks, WARN)
    assert exit_code(checks) == 0


def test_no_metric_questions_passes(tmp_path: Path):
    root = filled(tmp_path)
    m = yaml.safe_load((root / "profile" / "master.yaml").read_text())
    m.pop("metric_questions", None)
    (root / "profile" / "master.yaml").write_text(yaml.safe_dump(m))
    checks = doctor(root)
    assert any(c.name == "metric_questions" and c.level == PASS for c in checks)


def test_metric_question_for_unknown_bullet_warns(tmp_path: Path):
    root = filled(tmp_path)
    m = yaml.safe_load((root / "profile" / "master.yaml").read_text())
    m["metric_questions"] = [{"bullet_id": "ghost.1", "question": "How many?"}]
    (root / "profile" / "master.yaml").write_text(yaml.safe_dump(m))
    warns = text_of(doctor(root), WARN)
    assert "ghost.1" in warns and "not a bullet in profile/master.yaml" in warns


def test_personalize_keeps_metric_questions_on_renamed_ids(tmp_path: Path):
    m = yaml.safe_load((filled(tmp_path) / "profile" / "master.yaml").read_text())
    ids = {b["id"] for e in m["experience"] + m["projects"] for b in e["bullets"]}
    assert m["metric_questions"] and all(q["bullet_id"] in ids for q in m["metric_questions"])


def test_estimate_flag_without_tilde_number_warns(tmp_path: Path):
    root = filled(tmp_path)
    m = yaml.safe_load((root / "profile" / "master.yaml").read_text())
    m["experience"][0]["bullets"][1]["estimate"] = True        # northwind.2: "... used by 40 analysts ..."
    (root / "profile" / "master.yaml").write_text(yaml.safe_dump(m))
    warns = text_of(doctor(root), WARN)
    assert "northwind.2 has estimate: true but no ~number" in warns
    m["experience"][0]["bullets"][1]["text"] = m["experience"][0]["bullets"][1]["text"].replace("40", "~40")
    (root / "profile" / "master.yaml").write_text(yaml.safe_dump(m))
    assert "estimate: true" not in text_of(doctor(root), WARN)


# --- **bold** markup in bullet text ---------------------------------------------------------------------

def _edit_master(root: Path, fn) -> None:
    p = root / "profile" / "master.yaml"
    m = yaml.safe_load(p.read_text())
    fn(m)
    p.write_text(yaml.safe_dump(m, sort_keys=False))


def test_valid_bold_markup_passes(tmp_path: Path):
    root = filled(tmp_path)
    _edit_master(root, lambda m: m["experience"][0]["bullets"][0].update(text="Built **FastAPI** for **2 million** events"))
    checks = doctor(root)
    assert "bold_markup" not in text_of(checks, FAIL) and "bold_markup" not in text_of(checks, WARN)
    assert any(c.name == "bold_markup" and c.level == PASS for c in checks)


@pytest.mark.parametrize("where", ["text", "variant", "summary"])
def test_unbalanced_bold_markup_fails(tmp_path: Path, where: str):
    root = filled(tmp_path)

    def edit(m):
        b = m["experience"][0]["bullets"][1]
        if where == "text":
            b["text"] = "Shipped a **React dashboard used by 40 analysts"
        elif where == "variant":
            b["variants"] = {"short": "Shipped a **React** dashboard for **40 analysts"}
        else:
            m["summary_variants"]["general"] = "Engineer using ****."
    _edit_master(root, edit)
    fails = text_of(doctor(root), FAIL)
    assert "bold_markup" in fails
    want = {"text": "northwind.2.text", "variant": "northwind.2.variants.short", "summary": "summary_variants.general"}
    assert want[where] in fails, fails


def test_bold_in_narratives_warns(tmp_path: Path):
    root = filled(tmp_path)
    _edit_master(root, lambda m: m["narratives"][0].update(text="Likes **owning** a product end to end."))
    warns = text_of(doctor(root), WARN)
    assert "bold_markup" in warns and "narratives" in warns


def test_bold_marked_estimate_counts_as_tilde_number(tmp_path: Path):
    root = filled(tmp_path)

    def edit(m):
        b = m["experience"][0]["bullets"][1]
        b["estimate"] = True
        b["text"] = "Shipped a React and TypeScript dashboard used by **~40 analysts** to review reconciliation breaks"
    _edit_master(root, edit)
    assert "estimate: true" not in text_of(doctor(root), WARN)


def test_yaml_alias_error_hints_to_quote_bold(tmp_path):
    from conftest import make_temp_root
    from careeros.doctor import run_doctor
    root = make_temp_root(tmp_path / "repo")
    p = root / "profile" / "master.yaml"
    p.write_text(p.read_text().replace("summary_variants:", "bad: **Python** first\nsummary_variants:", 1))
    msgs = [c.detail for c in run_doctor(root) if c.name == "yaml"]
    assert any("must be quoted" in m for m in msgs), msgs


# `**` outside bullet text / variants / summary_variants: render.py exits 1 on it, so doctor must FAIL first
@pytest.mark.parametrize("path, edit", [
    ("skills.programming[0]", lambda m: m["skills"]["programming"].__setitem__(0, "**Python**")),
    ("experience[0].title", lambda m: m["experience"][0].update(title="**Software** Engineer")),
    ("experience[0].stack[1]", lambda m: m["experience"][0]["stack"].__setitem__(1, "**FastAPI**")),
    ("education[0].degree", lambda m: m["education"][0].update(degree="**Bachelor** of Science")),
    ("identity.name", lambda m: m["identity"].update(name="**Alex** Example")),
])
def test_bold_outside_bullets_and_summaries_fails_with_path(tmp_path: Path, path: str, edit):
    root = filled(tmp_path)
    _edit_master(root, edit)
    fails = [c.detail for c in doctor(root) if c.name == "bold_markup" and c.level == FAIL]
    assert any(path in f and "only in bullet text" in f for f in fails), fails


@pytest.mark.parametrize("where", ["text", "variant", "summary"])
def test_valid_bold_in_allowed_fields_passes(tmp_path: Path, where: str):
    root = filled(tmp_path)

    def edit(m):
        b = m["experience"][0]["bullets"][1]
        if where == "text":
            b["text"] = "Shipped a **React** dashboard used by **40 analysts**"
        elif where == "variant":
            b["variants"] = {"short": "Shipped a **React** dashboard"}
        else:
            m["summary_variants"]["general"] = "Engineer shipping **Python** services."
    _edit_master(root, edit)
    checks = [c for c in doctor(root) if c.name == "bold_markup"]
    assert [c.level for c in checks] == [PASS], checks


def test_bold_in_narratives_only_warns(tmp_path: Path):
    root = filled(tmp_path)
    _edit_master(root, lambda m: m["narratives"][0].update(text="Likes **owning** a product end to end."))
    levels = {c.level for c in doctor(root) if c.name == "bold_markup"}
    assert levels == {WARN}


@pytest.mark.parametrize("where", ["variant", "summary", "variant_bracket"])
def test_bold_in_dotted_variant_keys_passes(tmp_path: Path, where: str):
    root = filled(tmp_path)

    def edit(m):
        b = m["experience"][0]["bullets"][1]
        if where == "variant":
            b["variants"] = {"long.v2": "Moved **three** services to Kubernetes"}
        elif where == "variant_bracket":
            b["variants"] = {"alt[1]": "Moved **three** services to Kubernetes"}
        else:
            m["summary_variants"]["backend.v2"] = "**Python** engineer shipping services."
    _edit_master(root, edit)
    checks = [c for c in doctor(root) if c.name == "bold_markup"]
    assert [c.level for c in checks] == [PASS], checks


def test_bold_in_a_skill_under_a_dotted_key_still_fails(tmp_path: Path):
    root = filled(tmp_path)
    _edit_master(root, lambda m: m.setdefault("skills", {}).update({"lang.v2": ["**Python**"]}))
    fails = [c for c in doctor(root) if c.name == "bold_markup" and c.level == FAIL]
    assert fails and "lang.v2" in fails[0].detail


# --- runs / llm config (careeros.runs.config) ---------------------------------------------------------------

def test_check_runs_passes_on_the_example_pipeline():
    from careeros.doctor import check_runs

    cfg = yaml.safe_load((EXAMPLE_REPO / "config" / "pipeline.yaml").read_text())
    checks = check_runs(cfg)
    assert [(c.level, c.name) for c in checks] == [(PASS, "runs"), (PASS, "schedule")]


def test_check_runs_fails_on_old_cron_schedule():
    from careeros.doctor import check_runs

    checks = check_runs({"schedule": {"scout": "0 7 * * *"}})
    assert checks[-1].level == FAIL and checks[-1].name == "schedule" and "schedule.jobs" in checks[-1].detail


def test_check_runs_fails_on_a_bad_budget():
    from careeros.doctor import check_runs

    (c,) = check_runs({"runs": {"preset": "huge"}})
    assert c.level == FAIL and "runs.preset" in c.detail


def test_check_runs_warns_when_headless_cmd_does_not_stream():
    from careeros.doctor import check_runs

    checks = check_runs({"llm": {"headless_cmd": ["claude", "-p", "--output-format", "json"]}})
    assert [c.level for c in checks] == [WARN]
    assert "stream-json" in checks[0].detail


def test_run_doctor_reports_runs_config(tmp_path):
    root = tmp_path / "r"
    import shutil as _sh
    _sh.copytree(EXAMPLE_REPO / "config", root / "config")
    _sh.copytree(EXAMPLE_REPO / "profile", root / "profile")
    p = root / "config" / "pipeline.yaml"
    data = yaml.safe_load(p.read_text())
    data["runs"] = {"max_consecutive_failures": 0}
    p.write_text(yaml.safe_dump(data))
    fails = [c for c in run_doctor(root, which=lambda t: "/bin/" + t, examples=EXAMPLE_REPO) if c.name == "runs"]
    assert fails and fails[0].level == FAIL
