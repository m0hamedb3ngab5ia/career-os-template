---
name: verify-careeros
description: Drive and prove the career-os local web UI (`careeros ui`, FastAPI + static bundle on 127.0.0.1) and its CLI on a disposable fictional-candidate copy. Use to confirm a change works in the real app (Today, Jobs, Profile › Résumés, Settings), not just in tests.
---

# Verify career-os

Surface: local web UI `careeros ui` (primary); CLI `careeros ...` (secondary, see CLAUDE.md Commands). Read `features/README.md`, then the feature file you need.

Isolation: the user's real instance may run on port 8765. Never drive, curl-write or kill it. Use port **8799** only. Run from a checkout/worktree; the app root is `CAREEROS_ROOT` or the nearest ancestor with `config/` (so the checkout itself). `careeros init` copies `examples/` (fictional candidate "Alex Example") into gitignored `profile/ config/ data/` of that checkout. Never point `CAREEROS_ROOT` at a private repo.

## Launch

```bash
W=$(git rev-parse --show-toplevel); cd $W
PY=<path to a venv>/bin   # shared .venv, or: python3 -m venv .venv && .venv/bin/pip install -e ".[ui,test]" -q
export PYTHONPATH=src CAREEROS_ROOT=$W      # worktree: shared .venv would import another checkout's src
$PY/careeros init                            # idempotent, never overwrites
EV=${TMPDIR:-/tmp}/verify-careeros/$(date +%Y%m%d-%H%M%S); mkdir -p $EV; echo $EV > $EV/../latest
# PATH without `claude`: uploads/reviews must never spawn a real LLM run
(PATH=/usr/bin:/bin nohup $PY/python -m careeros.cli ui --port 8799 --no-open >$EV/server.log 2>&1 & echo $! > $EV/pid)
sleep 4; curl -s 127.0.0.1:8799/api/health      # ready: {"ok":true,"version":...}
```

Ready also = log line `careeros ui: http://127.0.0.1:8799`. Static bundle is committed (`src/careeros/ui/static`), no npm needed. Startup indexes jobs into `data/careeros.db` (disposable).

## Doctor

Read-only; run first whenever anything looks off:

```bash
$PY/careeros doctor --quiet | tail -3     # exit 1 + "example_data" FAILs is EXPECTED on the fictional copy; a Python traceback / "run careeros init" is not
curl -s 127.0.0.1:8799/api/health         # ok:true, config_error:null
lsof -nP -iTCP:8799 -sTCP:LISTEN          # PID must equal $(cat $EV/pid); else not ours: stop, do not drive
```

## Drive

Browser: in-app browser MCP (`mcp__Claude_Browser__navigate`, `find`, `read_page`, `get_page_text`, `computer`). Routes: `/` Today, `/jobs`, `/jobs/<id>`, `/profile#resumes`, `/settings/<section>`, `/automation`, `/actions`, `/pipeline`. Sidebar nav: `aria-label="Sections"`. First visit shows a product tour dialog: click `Skip tour` first.

API writes (curl) need header `X-CareerOS: 1`; reads do not. The MCP browser cannot fill a native file input, so uploads go through the same endpoint the `Upload résumé` button calls (`PUT /api/profile/resumes?filename=`), then the UI is checked for the result. Say so in the proof.

Runs that need LLMs (review, extract-master, apply-edit, redraft, prepare, score) need `claude` headless. With `claude` off PATH, or example data still present, the run stops with `stop_reason: doctor_failed`: the UI then shows "The review failed. Retry review". Prove only deterministic parts; mark LLM steps "not proven (needs claude)".

## Evidence

Directory `$EV` (`$TMPDIR/verify-careeros/<timestamp>/`, outside the worktree, survives cleanup; `$EV/../latest` names it). Per proof save: `server.log`, curl request + response bodies (`*.json`), UI text from `get_page_text`/`read_page` pasted into `notes.md` with feature ID and entry point, and a screenshot (browser MCP screenshots land in the tool-results dir; copy to `$EV`, or note them, then `rm` scratch copies elsewhere).

Standards: exercise the real user path (UI route, real endpoint), not setters or test endpoints. Capture the action and the resulting state. Verify side effects on disk (e.g. `profile/resumes/<rid>/v1/{original.*,text.txt,ats.json}`) next to what the UI shows. Mocks only at production boundaries. `apply fill` is not a dry run: it opens Chromium and the network, so do not prove it here.

## Cleanup

```bash
PID=$(cat $EV/pid)
lsof -nP -iTCP:8799 -sTCP:LISTEN | grep -q " $PID " && kill $PID    # only the PID we started; never pkill
sleep 2; lsof -nP -iTCP:8799 -sTCP:LISTEN | wc -l                  # expect 0
rm -rf profile config data CLAUDE.local.md                           # created by init in the checkout (all gitignored)
git status --short                                                   # expect clean (plus your intended edits)
ls $EV                                                               # evidence still there
```

Run cleanup after every failed attempt too. Do not remove `$EV`. Leave the in-app browser tab alone (or navigate to `about:blank`).

## Helpers

None shipped; everything above is plain shell and the browser MCP.
