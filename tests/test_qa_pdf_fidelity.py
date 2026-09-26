"""Unit tests for careeros.qa_ext.pdf_fidelity (resume.pdf vs resume.txt / profile identity).

PDFs are built in-test with pypdf only: a hand-written content stream (one Tj per line), optional
URI link annotations, optional /Info metadata and an optional (fake) embedded font file.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from conftest import EXAMPLE_REPO

from careeros.qa import Checker
from careeros.qa_ext.pdf_fidelity import check_pdf_fidelity, normalize_text, text_tokens

pytestmark = pytest.mark.unit

pypdf = pytest.importorskip("pypdf")

RESUME_TXT = """Alex Example
Springfield, NY | 555-010-0199 | alex@example.com
https://linkedin.com/in/alex-example | https://github.com/alex-example

EXPERIENCE
Acme | Jun 2026 - Present
Software Engineer | New York, NY
- Built a FastAPI service in Python that ingests Kafka order events into PostgreSQL, processing 2 million events per day
- Shipped a React and TypeScript dashboard used by 40 analysts to review reconciliation breaks
- Contributed to containerizing three services with Docker and deploying them to AWS as a member of the platform team

Initech | Jun 2025 - Aug 2025
Data Engineering Intern | Boston, MA
- Wrote 12 Airflow DAGs in Python moving SQL reports into a warehouse, cutting manual prep by 5 hours per week

EDUCATION
Springfield State University | Aug 2022 - May 2026
Bachelor of Science, Computer Science, GPA 3.6

SKILLS
Programming: Python, SQL, TypeScript, Swift
Tools & Platforms: PostgreSQL, Kafka, Docker, AWS, Airflow, Git
"""

GOOD_LINKS = ["mailto:alex@example.com", "https://linkedin.com/in/alex-example", "https://github.com/alex-example"]
GOOD_META = {"/Title": "Alex Example Resume", "/Author": "Alex Example"}


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(path: Path, text: str, links: list[str] | None = None, meta: dict[str, str] | None = None,
             embedded: bool = True) -> Path:
    from pypdf.annotations import Link
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject, StreamObject

    w = pypdf.PdfWriter()
    page = w.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"), NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
    })
    if embedded:
        ff = StreamObject()
        ff.set_data(b"fake font program")
        desc = DictionaryObject({
            NameObject("/Type"): NameObject("/FontDescriptor"), NameObject("/FontName"): NameObject("/Helvetica"),
            NameObject("/Flags"): NumberObject(32), NameObject("/FontFile3"): w._add_object(ff),
        })
        font[NameObject("/FontDescriptor")] = w._add_object(desc)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): w._add_object(font)})})
    ops = ["BT /F1 9 Tf 11 TL 40 760 Td"]
    for line in text.splitlines():
        ops.append(f"({_esc(line)}) Tj T*")
    ops.append("ET")
    cs = DecodedStreamObject()
    cs.set_data("\n".join(ops).encode("latin-1"))
    page[NameObject("/Contents")] = w._add_object(cs)
    for i, url in enumerate(links or []):
        w.add_annotation(0, Link(rect=(40, 700 - 20 * i, 200, 712 - 20 * i), url=url))
    if meta:
        w.add_metadata(meta)
    with path.open("wb") as fh:
        w.write(fh)
    return path


def make_job(tmp_path: Path, pdf_text: str | None = RESUME_TXT, resume_txt: str = RESUME_TXT,
             links: list[str] | None = None, meta: dict[str, str] | None = None, embedded: bool = True) -> Path:
    job = tmp_path / "jobs" / "t1"
    job.mkdir(parents=True)
    (job / "resume.txt").write_text(resume_txt)
    if pdf_text is not None:
        make_pdf(job / "resume.pdf", pdf_text, GOOD_LINKS if links is None else links,
                 GOOD_META if meta is None else meta, embedded)
    return job


def run(job: Path, cfg: dict | None = None) -> Checker:
    ck = Checker(job, EXAMPLE_REPO)
    if cfg is not None:
        ck.qa_cfg = {**(ck.qa_cfg or {}), "pdf": cfg}
    check_pdf_fidelity(ck)
    return ck


def by_name(ck: Checker, name: str) -> dict:
    for c in ck.checks:
        if c["check"] == name:
            return c
    raise AssertionError(f"check {name} not in {[c['check'] for c in ck.checks]}")


ALL = ("pdf_links_clickable", "pdf_text_matches_resume", "pdf_fonts_embedded", "pdf_metadata")


# --- pass / skip ------------------------------------------------------------------------------

def test_clean_pdf_passes_every_check(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path))
    for name in ALL:
        c = by_name(ck, name)
        assert c["ok"] and not c.get("skipped"), (name, c["detail"])
    ex = ck.extras["pdf_fidelity"]
    assert ex["text_recall"] == 1.0 and ex["missing_tokens"] == [] and ex["extra_tokens"] == []
    assert ex["links_missing"] == [] and ex["fonts_not_embedded"] == []
    assert ex["metadata"] == {"title": "Alex Example Resume", "author": "Alex Example"}
    assert ex["file_name"] == "resume.pdf"


def test_levels(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path))
    assert by_name(ck, "pdf_links_clickable")["level"] == "hard"
    assert by_name(ck, "pdf_fonts_embedded")["level"] == "soft"
    assert by_name(ck, "pdf_metadata")["level"] == "soft"


def test_missing_pdf_skips_all(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path, pdf_text=None))
    for name in ALL:
        assert by_name(ck, name).get("skipped") and by_name(ck, name)["ok"]
    assert ck.extras["pdf_fidelity"] == {"skipped": "resume.pdf not built"}


def test_unreadable_pdf_skips_without_duplicating_core_failure(tmp_path: Path) -> None:
    # Checker.check_pdf already hard-fails `pdf` on an unreadable file; this module must not crash or re-report
    job = make_job(tmp_path, pdf_text=None)
    (job / "resume.pdf").write_bytes(b"not a pdf")
    ck = run(job)
    for name in ALL:
        c = by_name(ck, name)
        assert c.get("skipped") and "unreadable" in c["detail"]
    assert "unreadable" in ck.extras["pdf_fidelity"]["skipped"]


def test_missing_resume_txt_skips_text_check_only(tmp_path: Path) -> None:
    job = make_job(tmp_path)
    (job / "resume.txt").unlink()
    ck = run(job)
    assert by_name(ck, "pdf_text_matches_resume").get("skipped")
    assert by_name(ck, "pdf_links_clickable")["ok"] and not by_name(ck, "pdf_links_clickable").get("skipped")


# --- links -----------------------------------------------------------------------------------

def test_missing_link_annotation_fails_hard(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path, links=GOOD_LINKS[:2]))
    c = by_name(ck, "pdf_links_clickable")
    assert not c["ok"] and "github" in c["detail"]
    assert ck.extras["pdf_fidelity"]["links_missing"] == ["github"]


def test_no_links_at_all_fails(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path, links=[]))
    assert set(ck.extras["pdf_fidelity"]["links_missing"]) == {"email", "linkedin", "github"}


def test_wrong_link_target_fails(tmp_path: Path) -> None:
    links = ["mailto:alex@example.com", "https://linkedin.com/in/someone-else", "https://github.com/alex-example"]
    ck = run(make_job(tmp_path, links=links))
    c = by_name(ck, "pdf_links_clickable")
    assert not c["ok"] and "linkedin" in c["detail"] and "someone-else" in c["detail"]


def test_email_link_needs_mailto(tmp_path: Path) -> None:
    links = ["https://alex@example.com", *GOOD_LINKS[1:]]
    ck = run(make_job(tmp_path, links=links))
    assert ck.extras["pdf_fidelity"]["links_missing"] == ["email"]


def test_link_normalization_scheme_www_trailing_slash_case(tmp_path: Path) -> None:
    links = ["MAILTO:Alex@Example.com?subject=hi", "http://www.linkedin.com/in/alex-example/",
             "https://GitHub.com/alex-example"]
    ck = run(make_job(tmp_path, links=links))
    assert by_name(ck, "pdf_links_clickable")["ok"], by_name(ck, "pdf_links_clickable")["detail"]


def test_links_required_config_limits_fields(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path, links=GOOD_LINKS[:1]), cfg={"links_required": ["email"]})
    assert by_name(ck, "pdf_links_clickable")["ok"]


def test_profile_without_link_fields_is_ok(tmp_path: Path) -> None:
    job = make_job(tmp_path, links=[])
    ck = Checker(job, EXAMPLE_REPO)
    ck.profile.profile = {"identity": {"name": "Alex Example"}}
    check_pdf_fidelity(ck)
    assert by_name(ck, "pdf_links_clickable")["ok"]


# --- text fidelity ---------------------------------------------------------------------------

def test_dropped_bullet_fails_hard(tmp_path: Path) -> None:
    pdf = "\n".join(line for line in RESUME_TXT.splitlines() if "Shipped a React" not in line
                    and "Contributed to" not in line)
    ck = run(make_job(tmp_path, pdf_text=pdf))
    c = by_name(ck, "pdf_text_matches_resume")
    assert c["level"] == "hard" and not c["ok"]
    ex = ck.extras["pdf_fidelity"]
    assert ex["text_recall"] < 0.9
    assert "reconciliation" in ex["missing_tokens"]


def test_small_loss_is_soft_band(tmp_path: Path) -> None:
    # drop ~5% of tokens: below 0.97, above 0.9 -> soft warning, not hard
    pdf = RESUME_TXT.replace(", processing 2 million events per day", "")
    ck = run(make_job(tmp_path, pdf_text=pdf))
    c = by_name(ck, "pdf_text_matches_resume")
    r = ck.extras["pdf_fidelity"]["text_recall"]
    assert 0.9 <= r < 0.97, r
    assert c["level"] == "soft" and not c["ok"]


def test_thresholds_configurable(tmp_path: Path) -> None:
    pdf = RESUME_TXT.replace(", processing 2 million events per day", "")
    ck = run(make_job(tmp_path, pdf_text=pdf), cfg={"text_recall_hard": 0.5, "text_recall_soft": 0.5})
    assert by_name(ck, "pdf_text_matches_resume")["ok"]


def test_render_differences_are_normalized(tmp_path: Path) -> None:
    # LaTeX output: bullets "•" instead of "- ", en dashes, no "|" separators, smart quotes, hyphenated wrap
    pdf = (RESUME_TXT.replace("- Built", "\x95 Built").replace(" - Present", " \x96 Present")
           .replace(" | ", "   ").replace("containerizing", "contain-\nerizing"))
    ck = run(make_job(tmp_path, pdf_text=pdf))
    assert by_name(ck, "pdf_text_matches_resume")["ok"], ck.extras["pdf_fidelity"]
    assert ck.extras["pdf_fidelity"]["text_recall"] == 1.0


def test_kerning_split_words_are_recovered_but_reported(tmp_path: Path) -> None:
    # pypdf on tectonic output yields "A WS" / "EDUCA TION": not lost text, but an ATS may see two words
    pdf = RESUME_TXT.replace("EDUCATION", "EDUCA TION").replace("Docker, AWS", "Docker, A WS")
    ck = run(make_job(tmp_path, pdf_text=pdf))
    assert by_name(ck, "pdf_text_matches_resume")["ok"]
    ex = ck.extras["pdf_fidelity"]
    assert ex["text_recall"] == 1.0
    assert {"education", "aws"} <= set(ex["split_tokens"])
    c = by_name(ck, "pdf_text_split_words")
    assert c["level"] == "soft" and not c["ok"] and "aws" in c["detail"]


def test_extra_text_in_pdf_is_flagged_soft(tmp_path: Path) -> None:
    pdf = RESUME_TXT + "Kubernetes Terraform expert rockstar\n"
    ck = run(make_job(tmp_path, pdf_text=pdf))
    assert by_name(ck, "pdf_text_matches_resume")["ok"]
    c = by_name(ck, "pdf_hidden_text")
    assert c["level"] == "soft" and not c["ok"] and "kubernetes" in c["detail"]
    assert {"kubernetes", "terraform", "rockstar"} <= set(ck.extras["pdf_fidelity"]["extra_tokens"])


def test_missing_sample_is_capped(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path, pdf_text="Alex Example\n"), cfg={"missing_sample": 5})
    assert len(ck.extras["pdf_fidelity"]["missing_tokens"]) == 5


def test_empty_pdf_text_fails_hard(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path, pdf_text=""))
    c = by_name(ck, "pdf_text_matches_resume")
    assert c["level"] == "hard" and not c["ok"] and ck.extras["pdf_fidelity"]["text_recall"] == 0.0


def test_normalize_text_handles_ligatures_quotes_bullets_hyphens() -> None:
    raw = "Airﬂow conﬁg ‘smart’ “quotes” • item con-\nfigured soft­hyphen eﬀort"
    norm = normalize_text(raw)
    assert "airflow config" in norm and "'smart'" in norm and '"quotes"' in norm
    assert "configured" in norm and "softhyphen" in norm and "effort" in norm and "•" not in norm


def test_text_tokens_lowercase_words_and_numbers() -> None:
    assert text_tokens("Built 12 DAGs, cut prep by 5 hours/week; GPA 3.6 C++") == [
        "built", "12", "dags", "cut", "prep", "by", "5", "hours", "week", "gpa", "3.6", "c++"]


# --- fonts -----------------------------------------------------------------------------------

def test_unembedded_font_is_soft_warning(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path, embedded=False))
    c = by_name(ck, "pdf_fonts_embedded")
    assert c["level"] == "soft" and not c["ok"] and "Helvetica" in c["detail"]
    assert ck.extras["pdf_fidelity"]["fonts_not_embedded"] == ["Helvetica"]


# --- metadata --------------------------------------------------------------------------------

def test_missing_metadata_is_soft_warning(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path, meta={"/Producer": "xdvipdfmx"}))
    c = by_name(ck, "pdf_metadata")
    assert c["level"] == "soft" and not c["ok"]
    assert "Title" in c["detail"] and "Author" in c["detail"]


def test_author_must_be_candidate(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path, meta={"/Title": "Resume", "/Author": "Jordan Lee"}))
    c = by_name(ck, "pdf_metadata")
    assert not c["ok"] and "Jordan Lee" in c["detail"]


@pytest.mark.parametrize("value", ["LaTeX", "Untitled", "resume.tex", "Anonymous"])
def test_placeholder_title_flagged(tmp_path: Path, value: str) -> None:
    ck = run(make_job(tmp_path, meta={"/Title": value, "/Author": "Alex Example"}))
    c = by_name(ck, "pdf_metadata")
    assert not c["ok"] and "placeholder" in c["detail"]


def test_example_name_as_author_flagged_for_real_candidate(tmp_path: Path) -> None:
    # a personal profile whose PDF still says "Alex Example" (template default leaked into metadata)
    job = make_job(tmp_path, meta={"/Title": "Jordan Lee Resume", "/Author": "Alex Example"})
    ck = Checker(job, EXAMPLE_REPO)
    ck.profile.profile = {**ck.profile.profile,
                          "identity": {**ck.profile.profile["identity"], "name": "Jordan Lee"}}
    ck.prof_path = tmp_path / "profile" / "master.yaml"  # not inside examples/
    check_pdf_fidelity(ck)
    c = by_name(ck, "pdf_metadata")
    assert not c["ok"] and "Alex Example" in c["detail"]


def test_metadata_author_whitespace_and_case_tolerant(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path, meta={"/Title": "Resume of Alex Example", "/Author": "  alex   example "}))
    assert by_name(ck, "pdf_metadata")["ok"], by_name(ck, "pdf_metadata")["detail"]


def test_does_not_duplicate_core_pdf_checks(tmp_path: Path) -> None:
    names = {c["check"] for c in run(make_job(tmp_path)).checks}
    assert "pdf_page_count" not in names and "contact_intact:resume.pdf" not in names
