"""Stage a Greenhouse fill_plan.json in a real browser with Playwright: 0 LLM calls, read back every value.

STAGE ONLY: never clicks submit; the user reviews and submits. Playwright is the optional `[fast-apply]` extra.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from careeros.apply import browser
from careeros.apply.session import ApplySession

EMBED = "https://job-boards.greenhouse.io/embed/job_app?for={board}&token={token}"
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


def plan_problems(plan: dict[str, Any]) -> list[str]:
    """Reasons the plan must not be filled: sensitive fields, or legal/salary/EEO pauses with no answer."""
    if plan.get("blocked"):
        return [f"blocked (sensitive field): {'; '.join(plan['blocked'])}"]
    return [f"unanswered ({f['source']}): {f['label']}" for f in plan["fields"]
            if f.get("value") is None and str(f.get("source")).startswith("pause:")]


def job_url(plan: dict[str, Any]) -> str:
    return EMBED.format(board=plan["board"], token=plan["ats_job_id"])


def matches(t: str, value: Any, shown: str, field_id: str = "") -> bool:
    shown = shown.strip().lower()
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
    opt = (root.get_by_role("option", name=value, exact=True) if exact
           else root.get_by_role("option").filter(has_text=value))
    opt.first.click()


def _fill_one(root: Any, f: dict[str, Any]) -> bool:
    """Fill one plan row and read it back; True when the page shows the planned value."""
    fid, t, v = f["field_id"], f["type"], f["value"]
    loc = root.locator(f'[id="{fid}"]')
    if t in ("text", "textarea"):
        loc.fill(str(v))
        return loc.input_value() == str(v)
    if t == "file":
        loc.set_input_files(v)
        return loc.evaluate("e => e.files.length ? e.files[0].name : ''") == Path(v).name
    if t == "checkbox_group":
        box = root.locator(f'fieldset:has(input[type=checkbox][name="{fid}"], input[type=checkbox][name="{fid}[]"], '
                           f'input[type=checkbox][id^="{fid}_"])')
        for opt in v:
            box.get_by_label(opt, exact=True).check()
        return all(box.get_by_label(opt, exact=True).is_checked() for opt in v)
    if t in ("select", "multiselect", "select_async"):
        for one in v if isinstance(v, list) else [v]:
            _pick(root, loc, str(one), exact=t != "select_async")
        loc.press("Escape")  # an open menu blocks the next field (spike: set_input_files timed out)
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
    root = page.frame_locator(IFRAME).first if page.locator(IFRAME).count() else page
    filled, failed, skipped = 0, [], []
    for f in plan["fields"]:
        if f["type"] == "hidden" or f.get("value") in (None, "", []):
            if f["type"] != "hidden":
                skipped.append(f["label"])
            continue
        try:
            ok, err = _fill_one(root, f), "read-back mismatch"
        except Exception as e:  # Playwright timeout/strict-mode errors: record and keep filling the rest
            ok, err = False, str(e).splitlines()[0][:200]
        if ok:
            filled += 1
        else:
            failed.append({"field_id": f["field_id"], "label": f["label"], "error": err})
    summary = {"filled": filled, "failed": failed, "skipped": skipped, "fill_s": round(time.monotonic() - t0, 1)}
    page.screenshot(path=str(ApplySession.screenshot_dir(job_dir) / "fill.png"), full_page=True)
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
        summary = fill(plan, page, job_dir, url)
        tab_id = ctx.new_cdp_session(page).send("Target.getTargetInfo")["targetInfo"]["targetId"]
        browser.save_record(job_dir, tab_id=tab_id, url=page.url, cdp=cdp)
        page.bring_to_front()
        print(f"staged, not submitted ({summary['filled']} filled, {len(summary['failed'])} failed; "
              "fill_summary.json): review + submit in the open tab", file=sys.stderr)
        return summary  # leaving the block only disconnects: the browser and the tab stay open
