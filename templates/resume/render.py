#!/usr/bin/env python3
"""Render data/jobs/<id>/resume.json -> resume.tex (+ resume.pdf if a LaTeX engine exists) and resume.txt.

Standalone: only needs jinja2 (and pyyaml for the optional categories.yaml template lookup).

    .venv/bin/python templates/resume/render.py data/jobs/<id>/resume.json [--template default] [--no-pdf] [--txt-only]

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
    bad = check_placeholders(data)
    if bad:
        raise ValueError(f"placeholder text in resume.json: {', '.join(bad)}")
    tname = resolve_template(data, template)
    tfile = f"{tname}.tex" if not tname.endswith(".tex") else tname
    if not (HERE / tfile).exists():
        raise FileNotFoundError(f"template not found: {HERE / tfile}")
    ctx = escape_tree(data)
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
    bad = check_placeholders(d)
    if bad:
        raise ValueError(f"placeholder text in resume.json: {', '.join(bad)}")
    idn = d["identity"]
    lines: list[str] = [idn.get("name", "")]
    lines.append(_line(idn.get("location", ""), idn.get("phone", ""), idn.get("email", "")))
    lines.append(_line(idn.get("linkedin") or "", idn.get("github") or "", idn.get("website") or ""))
    lines.append("")
    if d.get("summary"):
        lines += ["SUMMARY", d["summary"], ""]
    for sec in d["sections"]:
        t = sec.get("type")
        if t == "experience" and d["experience"]:
            lines.append("EXPERIENCE")
            for e in d["experience"]:
                lines.append(_line(e.get("company", ""), f"{e.get('start', '')} - {e.get('end', '')}"))
                sub = e.get("title", "") + (f", {e['team']}" if e.get("team") else "")
                lines.append(_line(sub, e.get("location", "")))
                lines += [f"- {b['text']}" for b in e.get("bullets", [])]
                lines.append("")
        elif t == "projects" and d["projects"]:
            lines.append("PROJECTS")
            for p in d["projects"]:
                lines.append(_line(p.get("name", ""), p.get("date", "")))
                if p.get("stack"):
                    lines.append(", ".join(p["stack"]))
                if p.get("link"):
                    lines.append(p["link"])
                lines += [f"- {b['text']}" for b in p.get("bullets", [])]
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
        elif t == "skills" and d["skills"]:
            lines.append("SKILLS")
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
