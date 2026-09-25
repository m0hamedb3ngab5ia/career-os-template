from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from conftest import EXAMPLE_REPO, build_resume_json, load_script

pytestmark = pytest.mark.unit

resume = load_script("templates/resume/render.py")
cover = load_script("templates/cover_letter/render.py")


@pytest.fixture(autouse=True)
def _example_profile(monkeypatch):
    """Cover-letter identity comes from a profile; tests use the fictional example, never the checkout's profile/."""
    monkeypatch.setattr(cover, "PROFILE", EXAMPLE_REPO / "profile" / "master.yaml")

SPECIALS = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
    "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


@pytest.mark.parametrize("mod", [resume, cover], ids=["resume", "cover"])
@pytest.mark.parametrize("ch,out", list(SPECIALS.items()))
def test_latex_escape_each_special(mod, ch, out):
    assert mod.latex_escape(f"a{ch}b") == f"a{out}b"


@pytest.mark.parametrize("mod", [resume, cover], ids=["resume", "cover"])
def test_latex_escape_all_together_no_double_escape(mod):
    s = r"R&D 100% $5 #1 a_b {x} ~ ^ \ "
    out = mod.latex_escape(s)
    assert out == r"R\&D 100\% \$5 \#1 a\_b \{x\} \textasciitilde{} \textasciicircum{} \textbackslash{} "
    assert mod.latex_escape(None) == ""
    assert mod.latex_escape(42) == "42"


@pytest.mark.parametrize("mod", [resume, cover], ids=["resume", "cover"])
def test_typographic_quotes_and_dashes(mod):
    assert mod.latex_escape("2025–2026 — “ok” ‘x’") == "2025--2026 --- ``ok'' `x'"


def test_resume_nbsp_becomes_tie_after_escaping():
    assert resume.latex_escape("Mr. X ~") == r"Mr.~X \textasciitilde{}"


def test_url_escape_and_escape_tree_raw_keys():
    assert resume.url_escape("https://x.com/a_b#c%20{d}") == r"https://x.com/a_b\#c\%20\{d\}"
    tree = resume.escape_tree({"identity": {"email": "a_b@x.com", "name": "A&B"}, "list": ["50%", 3, None]})
    assert tree["identity"]["email"] == r"a\_b@x.com" and tree["identity"]["email_raw"] == "a_b@x.com"
    assert tree["identity"]["name"] == r"A\&B" and "name_raw" not in tree["identity"]
    assert tree["list"] == [r"50\%", 3, None]


@pytest.mark.parametrize("text", ["[FILL IN metric]", "Built [fill in] thing", "[OPEN: on-call story]"])
def test_placeholders_rejected(tmp_path: Path, text):
    data = build_resume_json(yaml.safe_load((EXAMPLE_REPO / "profile" / "master.yaml").read_text()), ["acme.1"])
    data["experience"][0]["bullets"].append({"id": "acme.4", "text": text})
    p = tmp_path / "resume.json"
    p.write_text(json.dumps(data))
    assert resume.check_placeholders(resume.load_resume(p)) == ["experience[0].bullets[1].text"]
    with pytest.raises(ValueError, match="placeholder"):
        resume.render(p, pdf=False)
    assert not (tmp_path / "resume.tex").exists()
    assert resume.main([str(p), "--no-pdf"]) == 1


def test_template_resolution_order(tmp_path: Path, monkeypatch):
    cats = tmp_path / "categories.yaml"
    cats.write_text("swe_backend: {resume_template: compact}\nbroken: not-a-dict-is-fine\n")
    monkeypatch.setattr(resume, "CATEGORIES_YAML", cats)
    d = {"meta": {"template": "meta_t", "category": "swe_backend"}}
    assert resume.resolve_template(d, "flag_t") == "flag_t"
    assert resume.resolve_template(d, None) == "meta_t"
    assert resume.resolve_template({"meta": {"category": "swe_backend"}}, None) == "compact"
    assert resume.resolve_template({"meta": {"category": "unknown"}}, None) == "default"
    assert resume.resolve_template({"meta": {}}, None) == "default"
    assert resume.resolve_template({}, None) == "default"
    monkeypatch.setattr(resume, "CATEGORIES_YAML", tmp_path / "missing.yaml")
    assert resume.resolve_template({"meta": {"category": "swe_backend"}}, None) == "default"


def test_unknown_template_is_an_error(tmp_path: Path):
    p = tmp_path / "resume.json"
    p.write_text(json.dumps({"identity": {"name": "A"}, "meta": {"template": "nope"}}))
    with pytest.raises(FileNotFoundError):
        resume.render(p, pdf=False)


def test_load_resume_defaults_and_section_sort(tmp_path: Path):
    p = tmp_path / "resume.json"
    p.write_text(json.dumps({"sections": [{"type": "skills", "order": 4}, {"type": "experience", "order": 1},
                                          {"type": "bogus"}]}))
    d = resume.load_resume(p)
    assert [s["type"] for s in d["sections"]] == ["experience", "skills", "bogus"]
    assert d["experience"] == [] and d["skills"] == {} and d["summary"] is None


def _txt(tmp_path: Path, data: dict) -> list[str]:
    p = tmp_path / "resume.json"
    p.write_text(json.dumps(data))
    return resume.render_txt(p).read_text().splitlines()


def test_txt_section_order_follows_sections(tmp_path: Path):
    data = build_resume_json(yaml.safe_load((EXAMPLE_REPO / "profile" / "master.yaml").read_text()),
                             ["acme.1", "widgetizer.1"])
    data["summary"] = "Backend engineer."
    data["sections"] = [{"type": "skills", "order": 1}, {"type": "education", "order": 2},
                        {"type": "projects", "order": 3}, {"type": "experience", "order": 4}, {"type": "awards", "order": 5}]
    lines = _txt(tmp_path, data)
    heads = [line for line in lines if line.isupper() and line.isalpha()]
    assert heads == ["SUMMARY", "SKILLS", "EDUCATION", "PROJECTS", "EXPERIENCE"]
    assert lines[0] == "Alex Example"
    assert lines[1] == "Springfield, NY | 555-010-0199 | alex@example.com"
    assert lines[2] == "https://linkedin.com/in/alex-example | https://github.com/alex-example"
    assert any(line.startswith("- Built a FastAPI service") for line in lines)
    assert "Programming: Python, SQL, TypeScript, JavaScript, Swift, Java" in lines


def test_txt_skips_empty_sections_and_default_order(tmp_path: Path):
    lines = _txt(tmp_path, {"identity": {"name": "A"}, "experience": [], "skills": {"tools": ["Git"]}, "sections": None})
    assert "EXPERIENCE" not in lines and "SKILLS" in lines and "Tools & Platforms: Git" in lines


# --- cover letter ------------------------------------------------------------------

FM = """---
job_id: j1
company: Acme & Co
role: Software Engineer, Backend
greeting: "Hi Payments team,"
date: 2026-09-24
sign_off: "Alex"
bullet_ids: [acme.1]
company_facts:
  - {fact: "Payments owns the ledger", source: posting}
---
"""


def _cl(tmp_path: Path, body: str, fm: str = FM) -> Path:
    p = tmp_path / "cover_letter.md"
    p.write_text(fm + body)
    return p


def test_frontmatter_parse(tmp_path: Path):
    meta, body = cover.parse(_cl(tmp_path, "\nFirst para.\n\nSecond\npara.\n"))
    assert meta["company"] == "Acme & Co" and meta["bullet_ids"] == ["acme.1"]
    assert str(meta["date"]) == "2026-09-24"
    assert meta["company_facts"][0]["source"] == "posting"
    assert cover.paragraphs(body) == ["First para.", "Second para."]


@pytest.mark.parametrize("text", ["No frontmatter here.", "---\ncompany: x\nno closing fence\n"])
def test_missing_frontmatter_rejected(tmp_path: Path, text):
    p = tmp_path / "cover_letter.md"
    p.write_text(text)
    with pytest.raises(ValueError, match="frontmatter"):
        cover.parse(p)
    assert cover.main([str(p), "--txt-only"]) == 1


def test_txt_adds_greeting_and_signoff_once(tmp_path: Path):
    out = cover.render_txt(_cl(tmp_path, "I built **a thing** at *Acme*, see [repo](https://x.com/r).\n\nThanks.\n"))
    paras = out.read_text().strip().split("\n\n")
    assert paras == ["Hi Payments team,", "I built a thing at Acme, see repo (https://x.com/r).", "Thanks.", "Alex"]
    out = cover.render_txt(_cl(tmp_path, "Hi Payments team,\n\nBody.\n\nAlex\n"))
    assert out.read_text().strip().split("\n\n") == ["Hi Payments team,", "Body.", "Alex"]


def test_empty_body_does_not_crash(tmp_path: Path):
    out = cover.render_txt(_cl(tmp_path, "\n"))
    assert out.read_text().strip().split("\n\n") == ["Hi Payments team,", "Alex"]


def test_inline_markdown_to_latex():
    s = cover.md_inline_to_latex("Built **R&D** tool, *50%* faster: [site_1](https://x.com/a_b#c)")
    assert s == r"Built \textbf{R\&D} tool, \textit{50\%} faster: \href{https://x.com/a_b\#c}{site\_1}"


def test_cover_tex_uses_profile_identity_escaped(tmp_path: Path, monkeypatch):
    prof = tmp_path / "me.yaml"
    prof.write_text("identity: {name: Jordan Real, email: j_r@example.org, phone: '555-0100'}\n")
    monkeypatch.setattr(cover, "PROFILE", prof)
    tex = cover.render(_cl(tmp_path, "Body 100%.\n"), pdf=False).read_text()
    assert r"\textbf{Jordan Real}" in tex and r"j\_r@example.org" in tex
    assert r"Acme \& Co \textbar{} Software Engineer, Backend" in tex
    assert r"Body 100\%." in tex and "Hi Payments team," in tex


def test_cover_without_profile_fails_even_with_frontmatter_identity(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(cover, "PROFILE", tmp_path / "missing" / "master.yaml")
    fm = FM.replace("---\n", "---\nidentity: {name: Mallory Fake, email: m@evil.example}\n", 1)
    p = _cl(tmp_path, "Body.\n", fm)
    assert cover.main([p.as_posix(), "--no-pdf"]) == 1
    assert "profile" in capsys.readouterr().err and not (tmp_path / "cover_letter.tex").exists()


# --- stale artifacts / compile failures -------------------------------------------------------------

def _resume_json(tmp_path: Path, extra: str | None = None) -> Path:
    data = build_resume_json(yaml.safe_load((EXAMPLE_REPO / "profile" / "master.yaml").read_text()), ["acme.1"])
    if extra:
        data["experience"][0]["bullets"].append({"id": "acme.1", "text": extra})
    p = tmp_path / "resume.json"
    p.write_text(json.dumps(data))
    return p


def test_txt_only_rejects_placeholders_and_writes_nothing(tmp_path: Path):
    p = _resume_json(tmp_path, "Cut latency by [FILL IN metric]")
    assert resume.main([p.as_posix(), "--txt-only"]) == 1
    assert not (tmp_path / "resume.txt").exists()


def _failing_engine(mod, monkeypatch):
    monkeypatch.setattr(mod, "find_engine", lambda: ("fake", ["sh", "-c", "echo '! LaTeX Error'; exit 1", "sh"]))


def test_resume_compile_failure_exits_1_and_removes_stale_pdf(tmp_path: Path, monkeypatch, capsys):
    p = _resume_json(tmp_path)
    (tmp_path / "resume.pdf").write_text("OLD")
    _failing_engine(resume, monkeypatch)
    assert resume.main([p.as_posix()]) == 1
    assert not (tmp_path / "resume.pdf").exists()
    assert "fake failed" in capsys.readouterr().err


def test_cover_compile_failure_exits_1_and_removes_stale_pdf(tmp_path: Path, monkeypatch):
    p = _cl(tmp_path, "Body paragraph.\n")
    (tmp_path / "cover_letter.pdf").write_text("OLD")
    _failing_engine(cover, monkeypatch)
    assert cover.main([p.as_posix()]) == 1
    assert not (tmp_path / "cover_letter.pdf").exists()


@pytest.mark.parametrize("mod,src", [(resume, "resume"), (cover, "cover")])
def test_no_engine_is_a_warning_but_drops_stale_pdf(tmp_path: Path, monkeypatch, capsys, mod, src):
    p = _resume_json(tmp_path) if src == "resume" else _cl(tmp_path, "Body.\n")
    stale = tmp_path / ("resume.pdf" if src == "resume" else "cover_letter.pdf")
    stale.write_text("OLD")
    monkeypatch.setattr(mod, "find_engine", lambda: None)
    assert mod.main([p.as_posix()]) == 0
    assert not stale.exists()  # an old PDF must never sit next to a newer .tex
    assert "no LaTeX engine" in capsys.readouterr().err


def test_engine_success_without_pdf_is_an_error(tmp_path: Path, monkeypatch):
    p = _resume_json(tmp_path)
    monkeypatch.setattr(resume, "find_engine", lambda: ("fake", ["true"]))
    assert resume.main([p.as_posix()]) == 1


def test_cover_identity_comes_from_profile_not_frontmatter(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(cover, "PROFILE", EXAMPLE_REPO / "profile" / "master.yaml")
    fm = FM.replace("---\n", "---\nidentity: {name: Mallory Fake, email: m@evil.example, phone: '999'}\n", 1)
    tex = cover.render(_cl(tmp_path, "Body.\n", fm), pdf=False).read_text()
    assert r"\textbf{Alex Example}" in tex
    assert "Mallory" not in tex and "evil.example" not in tex
    assert "ignoring frontmatter identity" in capsys.readouterr().err


@pytest.mark.parametrize("mod,src,flag", [(resume, "resume", "--no-pdf"), (resume, "resume", "--txt-only"),
                                          (cover, "cover", "--no-pdf"), (cover, "cover", "--txt-only")])
def test_modes_without_pdf_drop_stale_pdf(tmp_path: Path, monkeypatch, mod, src, flag):
    if src == "cover":
        monkeypatch.setattr(cover, "PROFILE", EXAMPLE_REPO / "profile" / "master.yaml")
    p = _resume_json(tmp_path) if src == "resume" else _cl(tmp_path, "Body.\n")
    stale = tmp_path / ("resume.pdf" if src == "resume" else "cover_letter.pdf")
    stale.write_text("OLD")
    assert mod.main([p.as_posix(), flag]) == 0
    assert not stale.exists()


def test_validation_failure_also_drops_stale_pdf(tmp_path: Path):
    p = _resume_json(tmp_path, "Cut latency by [FILL IN metric]")
    (tmp_path / "resume.pdf").write_text("OLD")
    assert resume.main([p.as_posix()]) == 1
    assert not (tmp_path / "resume.pdf").exists()
    bad = tmp_path / "cl" / "cover_letter.md"
    bad.parent.mkdir()
    bad.write_text("no frontmatter\n")
    (bad.parent / "cover_letter.pdf").write_text("OLD")
    assert cover.main([bad.as_posix()]) == 1
    assert not (bad.parent / "cover_letter.pdf").exists()


def test_cover_identity_follows_pipeline_profile_path(tmp_path: Path, monkeypatch):
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "profile").mkdir()
    (root / "config" / "pipeline.yaml").write_text("paths:\n  profile: private/me.yaml\n")
    (root / "profile" / "master.yaml").write_text("identity: {name: Alex Example}\n")  # stale example copy
    (root / "private").mkdir()
    (root / "private" / "me.yaml").write_text("identity: {name: Jordan Real, email: j@example.org}\n")
    monkeypatch.setattr(cover, "REPO", root)
    monkeypatch.setattr(cover, "PROFILE", None)
    tex = cover.render(_cl(tmp_path, "Body.\n"), pdf=False).read_text()
    assert r"\textbf{Jordan Real}" in tex and "Alex Example" not in tex


@pytest.mark.parametrize("mod", [resume, cover], ids=["resume", "cover"])
def test_offline_env_makes_tectonic_cache_only(mod, monkeypatch):
    monkeypatch.setattr(mod.shutil, "which", lambda n: "/x/tectonic" if n == "tectonic" else None)
    monkeypatch.delenv("CAREEROS_LATEX_OFFLINE", raising=False)
    assert "--only-cached" not in mod.find_engine()[1]
    monkeypatch.setenv("CAREEROS_LATEX_OFFLINE", "1")
    assert "--only-cached" in mod.find_engine()[1]
