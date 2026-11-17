"""Fill one Ashby form field and read it back (called by gh_fill.fill when plan["ats"] == "ashby").

Every field sits in `[data-field-path="<path>"]`: text/textarea/date = an input, booleans = Yes/No buttons
(`data-option`, `aria-pressed`), multi-selects = checkboxes labelled with the option, location = an autocomplete
combobox, resume = a hidden file input. Never submits.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from careeros.apply.questions import select_eeo_option


# Required fields (label class has "required") with nothing entered: no text, no checked box/radio, no pressed
# Yes/No button, no uploaded file ("Replace" shows once one is attached).
EMPTY_REQUIRED_JS = """f => [...f.querySelectorAll('[data-field-path]')].filter(w => {
    const l = w.querySelector('label'); if (!l || !/required/i.test(l.className)) return false;
    if ([...w.querySelectorAll('input:not([type=file]):not([type=checkbox]):not([type=radio]), textarea')].some(i => i.value.trim())) return false;
    if (w.querySelector('input:checked, button[aria-pressed=true], button[class*=_active]')) return false;
    return ![...w.querySelectorAll('button')].some(b => /replace/i.test(b.textContent)); })
  .map(w => w.querySelector('label').textContent.trim().slice(0, 120))"""


def wrapper(root: Any, fid: str) -> Any:
    return root.locator(f'[data-field-path="{fid}"]')


def ready_selector() -> str:
    return '[data-field-path="_systemfield_email"] input'


def fill_one(root: Any, f: dict[str, Any]) -> bool:
    fid, t, v = f["field_id"], f["type"], f["value"]
    w = wrapper(root, fid)
    if t in ("text", "textarea", "date"):
        box = w.locator("input:not([type=file]):not([type=checkbox]), textarea").first
        box.fill(str(v))
        if t == "date":
            box.press("Enter")
        return box.input_value().strip() != "" if t == "date" else box.input_value() == str(v)
    if t == "file":
        w.locator("input[type=file]").set_input_files(v)
        w.get_by_text(Path(v).name).first.wait_for()
        return True
    if t == "boolean":
        btn = w.locator(f'button[data-option="{str(v).lower()}"]')
        btn.click()
        return btn.get_attribute("aria-pressed") == "true"
    if t == "checkbox_group":
        v = [v] if isinstance(v, str) else v  # one picked option may arrive as a plain string
        for opt in v:
            w.get_by_label(opt, exact=True).check()
        return all(w.get_by_label(opt, exact=True).is_checked() for opt in v)
    if t == "eeo":  # radios labelled with the option text; the first label is the question itself
        pick = select_eeo_option(v, w.locator("label").all_inner_texts(), f["eeo"])
        if not pick:
            raise LookupError(f"no EEO option for {v!r}")
        radio = w.get_by_label(pick, exact=True)
        radio.check()
        return radio.is_checked()
    if t == "location":
        city = str(v).split(",")[0].strip()
        box = w.get_by_role("combobox")
        box.click()
        box.fill(city)
        root.get_by_role("option").first.click()
        return city.lower() in box.input_value().lower()
    if t == "select":
        if w.locator("select").count():
            w.locator("select").select_option(label=str(v))
            return True
        btn = w.get_by_role("button", name=str(v), exact=True)
        if btn.count():
            btn.click()
            return btn.get_attribute("aria-pressed") in ("true", None)
        radio = w.get_by_label(str(v), exact=True)
        radio.check()
        return radio.is_checked()
    raise ValueError(f"unknown field type {t!r}")
