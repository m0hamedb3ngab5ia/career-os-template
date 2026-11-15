"""Headless fill of a saved Ashby-like form (static HTML mirroring jobs.ashbyhq.com's markup)."""
from __future__ import annotations

import pytest

from careeros.apply import gh_fill

pytestmark = pytest.mark.integration

HTML = """<form>
<div data-field-path="_systemfield_name"><label>Legal Name</label><input id="_systemfield_name" type="text"></div>
<div data-field-path="_systemfield_email"><input id="_systemfield_email" type="email"></div>
<div data-field-path="r"><input type="file" id="_systemfield_resume"><script>
document.querySelector('#_systemfield_resume').onchange=e=>{const s=document.createElement('span');
s.textContent=e.target.files[0].name;e.target.parentNode.appendChild(s)}</script></div>
<div data-field-path="auth"><button type="button" aria-pressed="false" data-option="yes">Yes</button>
<button type="button" aria-pressed="false" data-option="no">No</button></div>
<div data-field-path="pref"><fieldset><input type="checkbox" id="c0"><label for="c0">Remote - US</label>
<input type="checkbox" id="c1"><label for="c1">NYC</label></fieldset></div>
<script>document.querySelectorAll('[data-option]').forEach(b=>b.onclick=()=>{
document.querySelectorAll('[data-option]').forEach(x=>x.setAttribute('aria-pressed',x===b))})</script></form>"""


def test_fill_ashby_form_reads_back(tmp_path):
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    page_file = tmp_path / "form.html"
    page_file.write_text(HTML)
    rows = [("_systemfield_name", "text", "Alex Example"), ("_systemfield_email", "text", "a@example.com"),
            ("r", "file", str(pdf)), ("auth", "boolean", "Yes"), ("pref", "checkbox_group", ["NYC"]),
            ("gone", "text", "not on the page")]
    plan = {"ats": "ashby", "apply_url": page_file.as_uri(), "fields": [
        {"field_id": i, "label": i, "type": t, "value": v, "source": "profile"} for i, t, v in rows]}
    with gh_fill.sync_playwright() as p:
        b = p.chromium.launch()
        try:
            summary = gh_fill.fill(plan, b.new_page(), tmp_path)
        finally:
            b.close()
    assert summary["filled"] == 5 and summary["failed"] == []
    assert summary["skipped"] == ["gone (not on this form)"]
