#!/usr/bin/env python3
"""Render data/jobs/<id>/cover_letter.md -> cover_letter.txt (body only) and cover_letter.pdf (via LaTeX).

    .venv/bin/python templates/cover_letter/render.py data/jobs/<id>/cover_letter.md [--no-pdf] [--txt-only]

Input: Markdown with YAML frontmatter (see skeleton.md). Body paragraphs are separated by blank lines.
Supported inline Markdown: **bold**, *italic*, [text](url). Everything else is plain text.
Engine: tectonic if on PATH, else pdflatex, else warning and .tex left in place (exit 0).
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
PROFILE = HERE.parent.parent / "profile" / "master.yaml"
_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)

_ESC = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}
_TYPO = [("–", "--"), ("—", "---"), ("‘", "`"), ("’", "'"), ("“", "``"), ("”", "''")]


def latex_escape(s: Any) -> str:
    if s is None:
        return ""
    out = "".join(_ESC.get(c, c) for c in str(s))
    for a, b in _TYPO:
        out = out.replace(a, b)
    return out


def url_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", r"\%").replace("#", r"\#").replace("{", r"\{").replace("}", r"\}")


def parse(md_path: Path) -> tuple[dict[str, Any], str]:
    text = md_path.read_text(encoding="utf-8")
    m = _FM_RE.match(text)
    if not m:
        raise ValueError(f"{md_path}: missing YAML frontmatter (--- ... ---)")
    meta = yaml.safe_load(m.group(1)) or {}
    body = text[m.end():].strip("\n")
    return meta, body


def paragraphs(body: str) -> list[str]:
    paras = [re.sub(r"\s*\n\s*", " ", p).strip() for p in re.split(r"\n\s*\n", body)]
    return [p for p in paras if p]


_INLINE_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITAL = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")


def md_inline_to_latex(p: str) -> str:
    """Escape text but keep a few Markdown inline marks. Done by tokenising links first."""
    parts: list[str] = []
    pos = 0
    for m in _INLINE_LINK.finditer(p):
        parts.append(_fmt_text(p[pos:m.start()]))
        parts.append(r"\href{%s}{%s}" % (url_escape(m.group(2)), _fmt_text(m.group(1))))
        pos = m.end()
    parts.append(_fmt_text(p[pos:]))
    return "".join(parts)


def _fmt_text(s: str) -> str:
    # placeholders so escaping does not touch the markers
    s = _BOLD.sub(lambda m: "\x01" + m.group(1) + "\x02", s)
    s = _ITAL.sub(lambda m: "\x03" + m.group(1) + "\x04", s)
    s = latex_escape(s)
    return s.replace("\x01", r"\textbf{").replace("\x02", "}").replace("\x03", r"\textit{").replace("\x04", "}")


def strip_inline_md(p: str) -> str:
    p = _INLINE_LINK.sub(lambda m: f"{m.group(1)} ({m.group(2)})", p)
    p = _BOLD.sub(r"\1", p)
    p = _ITAL.sub(r"\1", p)
    return p


def _frame(meta: dict[str, Any], paras: list[str]) -> list[str]:
    """Add the frontmatter greeting / sign-off unless the body already has them (body may be empty)."""
    paras = list(paras)
    greeting = meta.get("greeting")
    if greeting and not (paras and paras[0].lower().startswith(greeting.lower()[:4])):
        paras.insert(0, greeting)
    sign = meta.get("sign_off")
    if sign and not (paras and paras[-1].strip() == sign.strip()):
        paras.append(sign)
    return paras


def render_txt(md_path: str | Path) -> Path:
    """Body only (greeting through sign-off), ready to paste into a form field."""
    src = Path(md_path).resolve()
    meta, body = parse(src)
    paras = _frame(meta, [strip_inline_md(p) for p in paragraphs(body)])
    out = src.with_name("cover_letter.txt")
    out.write_text("\n\n".join(paras) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return out


LETTER_TEX = r"""\documentclass[11pt,letterpaper]{article}
\usepackage[margin=1in]{geometry}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage{parskip}
\usepackage[hidelinks]{hyperref}
\pagestyle{empty}
\begin{document}
\noindent\textbf{%(name)s}\\
%(contact)s

\vspace{1em}
\noindent %(date)s

\noindent %(company_line)s

\vspace{1em}
%(body)s

\end{document}
"""


def render(md_path: str | Path, pdf: bool = True) -> Path:
    """cover_letter.md -> cover_letter.tex (+ .pdf when an engine exists). Returns the .tex path."""
    src = Path(md_path).resolve()
    meta, body = parse(src)
    paras = _frame(meta, paragraphs(body))
    body_tex = "\n\n".join(md_inline_to_latex(p) for p in paras)

    identity = _identity(meta)
    contact_bits = [identity.get(k) for k in ("location", "phone", "email", "linkedin") if identity.get(k)]
    company_line = latex_escape(meta.get("company", ""))
    if meta.get("role"):
        company_line += r" \textbar{} " + latex_escape(meta["role"])
    tex = LETTER_TEX % {
        "name": latex_escape(identity.get("name", "")),
        "contact": r" \textbar{} ".join(latex_escape(b) for b in contact_bits),
        "date": latex_escape(meta.get("date", "")),
        "company_line": company_line,
        "body": body_tex,
    }
    out = src.with_name("cover_letter.tex")
    out.write_text(tex, encoding="utf-8")
    print(f"wrote {out}")
    if pdf:
        p = compile_tex(out)
        if p:
            print(f"wrote {p}")
    return out


def _identity(meta: dict[str, Any]) -> dict[str, Any]:
    """Identity from profile/master.yaml (the only source of candidate facts). A frontmatter `identity:`
    block is used only when no profile exists (standalone rendering); otherwise it is ignored."""
    fm = meta.get("identity") if isinstance(meta.get("identity"), dict) else None
    if PROFILE.exists():
        try:
            ident = (yaml.safe_load(PROFILE.read_text(encoding="utf-8")) or {}).get("identity", {}) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"cannot parse {PROFILE}: {str(e).splitlines()[0]}") from None
        if fm:
            print("WARNING: ignoring frontmatter identity; using profile/master.yaml", file=sys.stderr)
        return ident
    return fm or {}


# --- engine (same logic as templates/resume/render.py) -------------------------

NO_ENGINE_MSG = "WARNING: no LaTeX engine; run `brew install tectonic`. Left .tex in place, no PDF produced."


def find_engine() -> tuple[str, list[str]] | None:
    if shutil.which("tectonic"):
        return "tectonic", ["tectonic", "--keep-logs", "-o", "."]
    if shutil.which("pdflatex"):
        return "pdflatex", ["pdflatex", "-interaction=nonstopmode", "-halt-on-error"]
    return None


class CompileError(RuntimeError):
    """A LaTeX engine is installed but did not produce the PDF."""


def compile_tex(tex_path: Path) -> Path | None:
    """None only when no engine is installed (a warning). Raises CompileError on failure.
    Any older PDF is removed first, so a PDF next to the .tex is always built from it."""
    pdf = tex_path.with_suffix(".pdf")
    pdf.unlink(missing_ok=True)
    engine = find_engine()
    if engine is None:
        print(NO_ENGINE_MSG, file=sys.stderr)
        return None
    name, cmd = engine
    proc = subprocess.run(cmd + [tex_path.name], cwd=tex_path.parent, capture_output=True, text=True)
    if proc.returncode != 0:
        pdf.unlink(missing_ok=True)
        raise CompileError(f"{name} failed on {tex_path}:\n{(proc.stdout + proc.stderr)[-3000:]}")
    for ext in (".aux", ".out"):
        p = tex_path.with_suffix(ext)
        if p.exists():
            p.unlink()
    if not pdf.exists():
        raise CompileError(f"{name} exited 0 but wrote no {pdf.name}")
    return pdf


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cover_letter_md")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--txt-only", action="store_true")
    a = ap.parse_args(argv)
    if a.txt_only or a.no_pdf:  # no PDF this run: never leave an older one next to the new text
        Path(a.cover_letter_md).resolve().with_name("cover_letter.pdf").unlink(missing_ok=True)
    try:
        if not a.txt_only:
            render(a.cover_letter_md, pdf=not a.no_pdf)
        render_txt(a.cover_letter_md)
    except (ValueError, FileNotFoundError, CompileError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
