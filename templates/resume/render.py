#!/usr/bin/env python3
"""Render data/jobs/<id>/resume.json -> resume.tex (+ resume.pdf if a LaTeX engine exists) and resume.txt.

Standalone: only needs jinja2 (and pyyaml for the optional categories.yaml template lookup).

    .venv/bin/python templates/resume/render.py data/jobs/<id>/resume.json [--template default] [--no-pdf] [--txt-only]

Bullet text and the summary may carry `**bold**` markup (src/careeros/markup.py): each span becomes
\\textbf{...} in resume.tex (inner text LaTeX-escaped) and the markers are dropped from resume.txt. Invalid
markup, or `**` in any other field, is an error (exit 1, nothing written).

Template selection order: --template flag > resume.json meta.template > categories.yaml[meta.category].resume_template > default.
Templates live in this directory as <name>.tex and use delimiters ((* *)), ((( ))), ((= =)).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

try:
    from careeros.markup import BULLET_SECTIONS, MARKER, bold_allowed, iter_strings, strip_bold, validate_bold
except ImportError:  # standalone checkout without the package installed: load the module file directly
    import importlib.util

    _spec = importlib.util.spec_from_file_location("_careeros_markup", REPO / "src" / "careeros" / "markup.py")
    _markup = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_markup)  # type: ignore[union-attr]
    MARKER, strip_bold, validate_bold = _markup.MARKER, _markup.strip_bold, _markup.validate_bold
    bold_allowed, iter_strings = _markup.bold_allowed, _markup.iter_strings
    BULLET_SECTIONS = _markup.BULLET_SECTIONS
CATEGORIES_YAML = REPO / "config" / "categories.yaml"

SECTION_ORDER_DEFAULT = ["experience", "projects", "education", "skills"]
URL_KEYS = {"email", "linkedin", "github", "website", "link"}
# "[FILL IN ...]" (tailor TODOs) and "[OPEN: ...]" (placeholder bullets in profile/master.yaml)
PLACEHOLDER_RE = re.compile(r"\[(FILL IN|OPEN\b)", re.I)

# --- LaTeX escaping ---------------------------------------------------------

_ESCAPES = [
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
]
_TYPO = [
    ("–", "--"),   # en dash
    ("—", "---"),  # em dash
    ("‘", "`"), ("’", "'"),
    ("“", "``"), ("”", "''"),
    (" ", "~"),
]


def latex_escape(s: Any) -> str:
    if s is None:
        return ""
    s = str(s)
    # backslash must go first; it is handled by the ordering of _ESCAPES
    out = []
    table = dict(_ESCAPES)
    for ch in s:
        out.append(table.get(ch, ch))
    s = "".join(out)
    for a, b in _TYPO:
        s = s.replace(a, b)
    return s


def latex_bold(s: Any) -> str:
    """latex_escape with `**x**` -> \\textbf{x}: split on the markers first, escape every piece, then wrap the
    bold pieces, so escaping never touches a marker and no `*` of a marker reaches LaTeX. Invalid markup
    raises ValueError."""
    if s is None:
        return ""
    err = validate_bold(s)
    if err:
        raise ValueError(f"invalid **bold** markup: {err}")
    parts = str(s).split(MARKER)
    return "".join(latex_escape(p) if i % 2 == 0 else r"\textbf{" + latex_escape(p) + "}" for i, p in enumerate(parts))


def url_escape(s: Any) -> str:
    """Escape for the URL argument of \\href{}: only %, #, and braces/backslash are dangerous."""
    if s is None:
        return ""
    s = str(s)
    return s.replace("\\", "\\\\").replace("%", r"\%").replace("#", r"\#").replace("{", r"\{").replace("}", r"\}")


def escape_tree(node: Any) -> Any:
    """Recursively escape every string. For URL-ish keys also add <key>_raw (href-safe)."""
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for k, v in node.items():
            if k in URL_KEYS and isinstance(v, str):
                out[k] = latex_escape(v)
                out[f"{k}_raw"] = url_escape(v)
            else:
                out[k] = escape_tree(v)
        return out
    if isinstance(node, list):
        return [escape_tree(x) for x in node]
    if isinstance(node, str):
        return latex_escape(node)
    return node


# --- data loading -------------------------------------------------------------

def load_resume(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("identity", {})
    data.setdefault("summary", None)
    data.setdefault("experience", [])
    data.setdefault("projects", [])
    data.setdefault("education", [])
    data.setdefault("skills", {})
    # Optional: ordered skill groups copied from the profile (the master résumé's categories). When present
    # they replace the four fixed `skills` keys; `skills_heading` names the section (default "Skills").
    data["skill_groups"] = [g for g in data.get("skill_groups") or [] if isinstance(g, dict) and g.get("items")]
    data["skills_heading"] = data.get("skills_heading") or "Skills"
    data.setdefault("meta", {})
    secs = data.get("sections") or [{"type": t, "order": i} for i, t in enumerate(SECTION_ORDER_DEFAULT, 1)]
    data["sections"] = sorted(secs, key=lambda s: s.get("order", 99))
    return data


def check_placeholders(data: dict[str, Any]) -> list[str]:
    hits: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str) and PLACEHOLDER_RE.search(node):
            hits.append(path)

    walk(data, "")
    return hits


def check_bold(data: dict[str, Any]) -> list[str]:
    """"<path>: <reason>" for invalid `**` markup in bullet text / summary, and for `**` in any other field
    (bold is allowed only in bullet text and the summary: markup.bold_allowed)."""
    errs: list[str] = []
    for path, s in iter_strings(data):
        if MARKER not in s:
            continue
        if not bold_allowed(path, "resume"):
            errs.append(f"{path}: '**' is allowed only in bullet text and the summary")
        elif (err := validate_bold(s)):
            errs.append(f"{path}: {err}")
    return errs


def _validate(data: dict[str, Any]) -> None:
    bad = check_placeholders(data)
    if bad:
        raise ValueError(f"placeholder text in resume.json: {', '.join(bad)}")
    bold = check_bold(data)
    if bold:
        raise ValueError("bold markup in resume.json: " + "; ".join(bold))


def resolve_template(data: dict[str, Any], explicit: str | None) -> str:
    if explicit:
        return explicit
    meta = data.get("meta") or {}
    if meta.get("template"):
        return str(meta["template"])
    cat = meta.get("category")
    if cat and CATEGORIES_YAML.exists():
        try:
            import yaml  # optional

            cats = yaml.safe_load(CATEGORIES_YAML.read_text(encoding="utf-8")) or {}
            t = (cats.get(cat) or {}).get("resume_template")
            if t:
                return str(t)
        except Exception:
            pass
    return "default"


# --- LaTeX engine ---------------------------------------------------------------

def find_engine() -> tuple[str, list[str]] | None:
    if shutil.which("tectonic"):
        # CAREEROS_LATEX_OFFLINE=1: never download the TeX bundle (tests; offline machines)
        offline = ["--only-cached"] if os.environ.get("CAREEROS_LATEX_OFFLINE") == "1" else []
        return "tectonic", ["tectonic", "--keep-logs", *offline, "-o", "."]
    if shutil.which("pdflatex"):
        return "pdflatex", ["pdflatex", "-interaction=nonstopmode", "-halt-on-error"]
    return None


NO_ENGINE_MSG = "WARNING: no LaTeX engine; run `brew install tectonic`. Left .tex in place, no PDF produced."


class CompileError(RuntimeError):
    """A LaTeX engine is installed but did not produce the PDF."""


def compile_tex(tex_path: Path) -> Path | None:
    """Compile tex -> pdf. None only when no engine is installed (a warning). Raises CompileError on failure.
    Any older PDF is removed first, so a PDF next to the .tex is always built from it."""
    pdf = tex_path.with_suffix(".pdf")
    pdf.unlink(missing_ok=True)
    engine = find_engine()
    if engine is None:
        print(NO_ENGINE_MSG, file=sys.stderr)
        return None
    name, cmd = engine
    workdir = tex_path.parent
    runs = 2 if name == "pdflatex" else 1
    for _ in range(runs):
        proc = subprocess.run(cmd + [tex_path.name], cwd=workdir, capture_output=True, text=True)
        if proc.returncode != 0:
            log_tail = (proc.stdout + proc.stderr)[-3000:]
            pdf.unlink(missing_ok=True)
            raise CompileError(f"{name} failed on {tex_path}:\n{log_tail}")
    # successful compile: drop build artefacts, including the engine log (it is kept only on failure)
    for ext in (".aux", ".out", ".log"):
        p = tex_path.with_suffix(ext)
        if p.exists():
            p.unlink()
    if not pdf.exists():
        raise CompileError(f"{name} exited 0 but wrote no {pdf.name}")
    return pdf


# --- renderers ---------------------------------------------------------------------

def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(HERE)),
        block_start_string="((*", block_end_string="*))",
        variable_start_string="(((", variable_end_string=")))",
        comment_start_string="((=", comment_end_string="=))",
        undefined=StrictUndefined,
        trim_blocks=True, lstrip_blocks=True,
        autoescape=False, keep_trailing_newline=True,
    )


def render(resume_json_path: str | Path, template: str | None = None, pdf: bool = True) -> Path:
    """resume.json -> resume.tex next to it. Compiles PDF when an engine exists. Returns the .tex path."""
    src = Path(resume_json_path).resolve()
    data = load_resume(src)
    _validate(data)
    tname = resolve_template(data, template)
    tfile = f"{tname}.tex" if not tname.endswith(".tex") else tname
    if not (HERE / tfile).exists():
        raise FileNotFoundError(f"template not found: {HERE / tfile}")
    ctx = escape_tree(data)
    # bullet text and the summary: escaped again from the raw value, with **bold** -> \textbf{}
    if isinstance(data.get("summary"), str):
        ctx["summary"] = latex_bold(data["summary"])
    for sec in BULLET_SECTIONS:
        for raw_e, e in zip(data.get(sec) or [], ctx.get(sec) or []):
            if not (isinstance(raw_e, dict) and isinstance(e, dict)):
                continue
            for raw_b, b in zip(raw_e.get("bullets") or [], e.get("bullets") or []):
                if isinstance(raw_b, dict) and isinstance(b, dict) and isinstance(raw_b.get("text"), str):
                    b["text"] = latex_bold(raw_b["text"])
    # identity fields the template always references
    for k in ("name", "email", "phone", "location", "linkedin", "github", "website"):
        ctx["identity"].setdefault(k, "")
        if k in URL_KEYS:
            ctx["identity"].setdefault(f"{k}_raw", "")
    for e in ctx["experience"]:
        for k in ("company", "title", "team", "location", "start", "end"):
            e.setdefault(k, "")
        e.setdefault("bullets", [])
    for p in ctx["projects"]:
        for k in ("name", "date", "link", "link_raw"):
            p.setdefault(k, "")
        p.setdefault("stack", [])
        p.setdefault("bullets", [])
    for ed in ctx["education"]:
        for k in ("school", "degree", "gpa", "location", "start", "end"):
            ed.setdefault(k, "")
        ed.setdefault("coursework", [])
        ed.setdefault("activities", [])
    for k in ("programming", "frameworks", "tools", "concepts"):
        ctx["skills"].setdefault(k, [])

    tex = _env().get_template(tfile).render(**ctx)
    out = src.with_name("resume.tex")
    out.write_text(tex, encoding="utf-8")
    print(f"wrote {out}")
    if pdf:
        p = compile_tex(out)
        if p:
            print(f"wrote {p}")
    return out


def _line(*parts: str, sep: str = " | ") -> str:
    return sep.join(p for p in parts if p)


def render_txt(resume_json_path: str | Path) -> Path:
    """resume.json -> resume.txt (plain text, ATS order). Returns the .txt path."""
    src = Path(resume_json_path).resolve()
    d = load_resume(src)
    _validate(d)
    idn = d["identity"]
    lines: list[str] = [idn.get("name", "")]
    lines.append(_line(idn.get("location", ""), idn.get("phone", ""), idn.get("email", "")))
    lines.append(_line(idn.get("linkedin") or "", idn.get("github") or "", idn.get("website") or ""))
    lines.append("")
    if d.get("summary"):
        lines += ["SUMMARY", strip_bold(d["summary"]), ""]
    for sec in d["sections"]:
        t = sec.get("type")
        if t == "experience" and d["experience"]:
            lines.append("EXPERIENCE")
            for e in d["experience"]:
                lines.append(_line(e.get("company", ""), f"{e.get('start', '')} - {e.get('end', '')}"))
                sub = e.get("title", "") + (f", {e['team']}" if e.get("team") else "")
                lines.append(_line(sub, e.get("location", "")))
                lines += [f"- {strip_bold(b['text'])}" for b in e.get("bullets", [])]
                lines.append("")
        elif t == "projects" and d["projects"]:
            lines.append("PROJECTS")
            for p in d["projects"]:
                lines.append(_line(p.get("name", ""), p.get("date", "")))
                if p.get("stack"):
                    lines.append(", ".join(p["stack"]))
                if p.get("link"):
                    lines.append(p["link"])
                lines += [f"- {strip_bold(b['text'])}" for b in p.get("bullets", [])]
                lines.append("")
        elif t == "education" and d["education"]:
            lines.append("EDUCATION")
            for ed in d["education"]:
                lines.append(_line(ed.get("school", ""), f"{ed.get('start', '')} - {ed.get('end', '')}"))
                deg = ed.get("degree", "") + (f", GPA {ed['gpa']}" if ed.get("gpa") else "")
                lines.append(_line(deg, ed.get("location", "")))
                if ed.get("coursework"):
                    lines.append("Coursework: " + ", ".join(ed["coursework"]))
                if ed.get("activities"):
                    lines.append("Activities: " + ", ".join(ed["activities"]))
                lines.append("")
        elif t == "skills" and d["skill_groups"]:
            lines.append(d["skills_heading"].upper())
            for g in d["skill_groups"]:
                lines.append(f"{g.get('label', '')}: " + ", ".join(str(x) for x in g["items"]))
            lines.append("")
        elif t == "skills" and d["skills"]:
            lines.append(d["skills_heading"].upper())
            for key, label in (("programming", "Programming"), ("frameworks", "Frameworks & Libraries"),
                               ("tools", "Tools & Platforms"), ("concepts", "Concepts")):
                if d["skills"].get(key):
                    lines.append(f"{label}: " + ", ".join(d["skills"][key]))
            lines.append("")
    out = src.with_name("resume.txt")
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("resume_json")
    ap.add_argument("--template", default=None, help="template name in templates/resume (without .tex)")
    ap.add_argument("--no-pdf", action="store_true", help="write .tex only, skip compilation")
    ap.add_argument("--txt-only", action="store_true", help="only write resume.txt")
    a = ap.parse_args(argv)
    # Any older PDF goes first: a failed or PDF-less run must never leave it next to newer sources.
    Path(a.resume_json).resolve().with_name("resume.pdf").unlink(missing_ok=True)
    try:
        if not a.txt_only:
            render(a.resume_json, template=a.template, pdf=not a.no_pdf)
        render_txt(a.resume_json)
    except (ValueError, FileNotFoundError, CompileError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
