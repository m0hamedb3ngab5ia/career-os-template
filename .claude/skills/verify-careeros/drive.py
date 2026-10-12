"""Tiny Playwright harness: steps.jsonl (name, app ms, clicks, url), screenshots, video, trace in $EV.
Use: PYTHONPATH=<skill dir> python - <<'X'
from drive import session
with session(EV) as (page, step):
    step("open", lambda: page.goto("/profile#resumes"), "text=Résumés")
X
App time = action until expect selector is visible; agent think time is outside the timer."""
import json, sys, time
from contextlib import contextmanager
from pathlib import Path
from playwright.sync_api import sync_playwright


@contextmanager
def session(ev, headless=True, base_url="http://127.0.0.1:8799"):
    ev = Path(ev)
    f = ev / "steps.jsonl"
    prev = [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []
    n = {"steps": len(prev), "clicks": prev[-1]["clicks"] if prev else 0}  # continue numbering across sessions
    log = f.open("a")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=headless)
        ctx = b.new_context(base_url=base_url, record_video_dir=str(ev / "video"), viewport={"width": 1280, "height": 800})
        ctx.tracing.start(screenshots=True, snapshots=True)
        page = ctx.new_page()

        def step(name, fn, expect=None, shot=True, click=False):
            t = time.perf_counter()
            fn()
            if expect:
                page.wait_for_selector(expect, timeout=15000)
            page.wait_for_load_state("networkidle")
            ms = round((time.perf_counter() - t) * 1000)
            n["steps"] += 1
            n["clicks"] += click
            if shot:
                page.screenshot(path=str(ev / f"{n['steps']:02d}-{name.replace(' ', '_')}.png"))
            rec = dict(step=n["steps"], name=name, app_ms=ms, clicks=n["clicks"], url=page.url, expect=expect)
            log.write(json.dumps(rec) + "\n"); log.flush()
            print(rec, file=sys.stderr)

        try:
            yield page, step
        finally:
            ctx.tracing.stop(path=str(ev / f"trace-{n['steps']:02d}.zip"))  # one per session
            ctx.close(); b.close(); log.close()
