"""Stage a Greenhouse fill_plan.json in a real browser with Playwright: 0 LLM calls, read back every value.

STAGE ONLY: never clicks submit; the user reviews and submits. Playwright is the optional `[fast-apply]` extra.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from careeros.apply import ashby_fill, browser
from careeros.apply.session import ApplySession

EMBED = "https://job-boards.greenhouse.io/embed/job_app?for={board}&token={token}"
# Required ("*") labelled inputs still empty after the fill: text with no value, a react-select with nothing picked.
EMPTY_REQUIRED_JS = """f => [...f.querySelectorAll('label')].filter(l => /\\*\\s*$/.test(l.textContent) && l.htmlFor)
  .filter(l => { const e = document.getElementById(l.htmlFor); if (!e || e.disabled || e.type === 'file' || e.type === 'hidden') return false;
    if (e.getAttribute('role') === 'combobox') { const c = e.closest('[class*=select__control]');
      return !(c && c.querySelector('[class*=single-value],[class*=multi-value]')); }
    return e.type === 'checkbox' ? false : !e.value; })
  .map(l => l.textContent.replace(/\\*\\s*$/, '').trim())"""
IFRAME = 'iframe#grnhse_iframe, iframe[src*="/embed/job_app"]'  # company careers pages embed the GH form


class MissingPlaywright(RuntimeError):
    pass


def sync_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright as sp
    except ImportError:
        raise MissingPlaywright("playwright is not installed: pip install -e '.[fast-apply]' && "
                                "playwright install chromium") from None
    return sp()


def preflight() -> None:
    """Raise MissingPlaywright when playwright or its Chromium is missing, so the UI refuses up front instead of
    spawning a detached fill that could only write the error to application.log."""
    with sync_playwright() as p:
        if not Path(p.chromium.executable_path).exists():
            raise MissingPlaywright("Playwright's Chromium is missing: playwright install chromium")


_CONSENT = re.compile(r"privacy|terms and conditions|terms of (use|service)|code of conduct|arbitration|acknowledg"
                      r"|consent|^i (agree|understand|confirm|acknowledge)", re.I)


def consent_fields(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Unanswered consent/acknowledgement fields: the candidate accepts these, never the filler. They don't block
    a fill; they stay blank for the user to tick before Submit."""
    return [f for f in plan["fields"] if f.get("value") in (None, "", []) and _CONSENT.search(str(f.get("label")))]


def plan_problems(plan: dict[str, Any]) -> list[str]:
    """Reasons the plan must not be filled: sensitive fields, legal/salary/EEO pauses with no answer, or a required
    field nobody answered yet (REQ-106: needs input; only optional fields may be skipped), or an AI draft the user
    has not approved or edited (REQ-105)."""
    if plan.get("blocked"):
        return [f"blocked (sensitive field): {'; '.join(plan['blocked'])}"]
    consents = {id(f) for f in consent_fields(plan)}
    empty = [f for f in plan["fields"] if f.get("value") in (None, "", []) and id(f) not in consents]
    return ([f"unanswered ({f['source']}): {f['label']}" for f in empty
             if str(f.get("source")).startswith("pause:") and not f.get("skipped")]
            + [f"needs input (required): {f['label']}" for f in empty
               if f.get("source") == "unanswered" and f.get("required") and not f.get("skipped")]
            + [f"unreviewed AI draft: {f['label']}" for f in plan["fields"]
               if f.get("source") == "ai_draft" and not f.get("reviewed") and not f.get("skipped")])


def job_url(plan: dict[str, Any]) -> str:
    if plan.get("ats") == "ashby":
        return plan["apply_url"]
    return EMBED.format(board=plan["board"], token=plan["ats_job_id"])


# GH degree options are fixed labels ("Bachelor's Degree", "Doctor of Philosophy (Ph.D.)"): profile prefix -> label text
DEGREE_KEYS = {"bachelor": "bachelor", "master": "master", "phd": "philosophy", "doctor": "philosophy",
               "associate": "associate", "high school": "high school"}


def degree_key(value: str) -> str | None:
    v = value.strip().lower().replace(".", "")
    return next((key for prefix, key in DEGREE_KEYS.items() if v.startswith(prefix)), None)


def matches(t: str, value: Any, shown: str, field_id: str = "") -> bool:
    shown = shown.strip().lower()
    if field_id.startswith("degree") and (key := degree_key(str(value))) and key in shown:
        return True
    if field_id == "country":  # ponytail: phone-country widget shows the dial code ("+1"), so only check non-empty
        return bool(shown)
    if isinstance(value, list):
        return all(str(v).lower() in shown for v in value)
    if t == "select_async":  # async options carry more text ("City, State, Country")
        return str(value).strip().lower() in shown
    return str(value).strip().lower() == shown


def _pick(root: Any, inp: Any, value: str, exact: bool) -> None:
    inp.click()
    inp.fill(value)
    lb = inp.get_attribute("aria-controls")  # read the list this input opens: the phone-country list is also in the DOM
    scope = root.locator(f'[id="{lb}"]') if lb else root
    opt = (scope.get_by_role("option", name=value, exact=True) if exact
           else scope.get_by_role("option").filter(has_text=value))
    try:
        opt.first.click()
    except Exception:
        raise LookupError(f"no option {value!r} after typing it") from None


def _fill_one(root: Any, f: dict[str, Any]) -> bool:
    """Fill one plan row and read it back; True when the page shows the planned value."""
    fid, t, v = f["field_id"], f["type"], f["value"]
    loc = root.locator(f'[id="{fid}"]')
    if t in ("text", "textarea"):
        loc.fill(str(v))
        return loc.input_value() == str(v)
    if t == "file":  # job-boards swaps the input for a filename chip once a file is picked: read that back
        loc.set_input_files(v)
        root.get_by_text(Path(v).name).first.wait_for(timeout=30_000)  # upload + resume parse can be slow
        return True
    if t == "checkbox":  # e.g. employment "Current role"
        loc.check()
        return loc.is_checked()
    if t == "checkbox_group" and root.locator(f'input[id="{fid}"][aria-autocomplete]').count():  # API says checkboxes, job-boards renders a react-select multiselect
        t = "multiselect"
    if t == "checkbox_group":
        box = root.locator(f'fieldset:has(input[type=checkbox][name="{fid}"], input[type=checkbox][name="{fid}[]"], '
                           f'input[type=checkbox][id^="{fid}_"])')
        for opt in v:
            box.get_by_label(opt, exact=True).check()
        return all(box.get_by_label(opt, exact=True).is_checked() for opt in v)
    if t in ("select", "multiselect", "select_async"):
        try:
            picked = False
            if fid.startswith("discipline") and isinstance(v, list):  # ordered fallback: first one offered wins
                for cand in v:
                    try:
                        _pick(root, loc, str(cand), exact=False)
                        v, picked = cand, True
                        break
                    except LookupError:
                        loc.press("Escape")  # a failed async search closes the menu: reset before the next one
                        continue
                else:
                    raise LookupError(f"none of {v!r} offered")
            for one in [] if picked else v if isinstance(v, list) else [v]:
                try:
                    _pick(root, loc, str(one), exact=t != "select_async" and fid != "country")  # "United States +1"
                except LookupError:  # "Bachelor of Engineering, X" has no option: pick the fixed label by keyword
                    if not (fid.startswith("degree") and (key := degree_key(str(one)))):
                        raise
                    _pick(root, loc, key, exact=False)
        finally:
            loc.press("Escape")  # an open menu (also after a failed pick) blocks the next field
        shown = loc.locator("xpath=ancestor::div[contains(@class, 'select__control')][1]").inner_text()
        return matches(t, v, shown, fid)
    raise ValueError(f"unknown field type {t!r}")


def fill(plan: dict[str, Any], page: Any, job_dir: str | Path, url: str | None = None) -> dict[str, Any]:
    """Fill every planned value in plan order (race appears only after hispanic), read back, 1 screenshot.
    Writes fill_summary.json next to fill_plan.json. Never submits."""
    t0 = time.monotonic()
    page.set_default_timeout(10_000)
    page.goto(url or job_url(plan))
    page.wait_for_load_state()
    ashby = plan.get("ats") == "ashby"
    root = page.frame_locator(IFRAME).first if not ashby and page.locator(IFRAME).count() else page
    try:  # the form is rendered client-side: wait for it before deciding a field is "not on this form"
        root.locator(ashby_fill.ready_selector() if ashby else '[id="email"]').first.wait_for()
    except Exception:
        pass
    filled, failed, skipped = 0, [], []
    hispanic = next((f.get("value") for f in plan["fields"] if f["field_id"] == "hispanic_ethnicity"), "No")
    for f in plan["fields"]:
        if f["field_id"] == "race" and hispanic != "No":  # job-boards shows race only after Hispanic/Latino = No
            skipped.append(f["label"])
            continue
        if f["type"] == "hidden" or f.get("value") in (None, "", []):
            if f["type"] != "hidden":
                skipped.append(f["label"])
            continue
        absent = (not ashby_fill.wrapper(root, f["field_id"]).count()) if ashby else (
            f.get("source") == "profile" and f["type"] not in ("file", "checkbox_group")
            and not root.locator(f'[id="{f["field_id"]}"]').count())
        if absent:
            skipped.append(f"{f['label']} (not on this form)")  # e.g. education_config hides school/dates
            continue
        try:
            ok, err = (ashby_fill.fill_one if ashby else _fill_one)(root, f), "read-back mismatch"
        except Exception as e:  # Playwright timeout/strict-mode errors: record and keep filling the rest
            ok, err = False, str(e).splitlines()[0][:200]
        if ok:
            filled += 1
        else:
            failed.append({"field_id": f["field_id"], "label": f["label"], "error": err})
    summary = {"filled": filled, "failed": failed, "skipped": skipped, "fill_s": round(time.monotonic() - t0, 1)}
    try:  # catch whole sections the plan never knew about (employment, consent selects)
        empty = root.locator("body" if ashby else "form").first.evaluate(
            ashby_fill.EMPTY_REQUIRED_JS if ashby else EMPTY_REQUIRED_JS)
        summary["empty_required"] = empty if isinstance(empty, list) else []
    except Exception as e:
        print(f"empty-required check skipped: {str(e).splitlines()[0][:200]}", file=sys.stderr)
    try:  # proof only: a slow full-page capture (background tab) must not fail a filled form
        page.screenshot(path=str(ApplySession.screenshot_dir(job_dir) / "fill.png"), full_page=True)
    except Exception as e:
        print(f"screenshot skipped: {str(e).splitlines()[0][:200]}", file=sys.stderr)
    (Path(job_dir) / "fill_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def run(plan: dict[str, Any], job_dir: str | Path, *, cdp: str | None, profile_dir: str | Path,
        url: str | None = None) -> dict[str, Any]:
    """Real use: fill in a new visible tab of the apply browser (your Chrome over `cdp`, or a detached dedicated
    profile on browser.DEFAULT_CDP), record the tab in application.json and return. The tab is never closed:
    you review and submit there, and it outlives this process and app rebuilds."""
    with sync_playwright() as p:
        if not cdp:
            cdp = browser.DEFAULT_CDP
            browser.ensure(cdp, profile_dir, p.chromium.executable_path)
        b = p.chromium.connect_over_cdp(cdp)
        ctx = b.contexts[0] if b.contexts else b.new_context()
        page = ctx.new_page()
        try:
            summary = fill(plan, page, job_dir, url)
        except Exception:
            page.close()  # our own fresh tab, no record saved yet: don't leave an orphan behind
            raise
        tab_id = ctx.new_cdp_session(page).send("Target.getTargetInfo")["targetInfo"]["targetId"]
        browser.save_record(job_dir, tab_id=tab_id, url=page.url, cdp=cdp)
        page.bring_to_front()
        print(f"{browser.STAGED} ({summary['filled']} filled, {len(summary['failed'])} failed; "
              "fill_summary.json): review + submit in the open tab", file=sys.stderr)
        return summary  # leaving the block only disconnects: the browser and the tab stay open
