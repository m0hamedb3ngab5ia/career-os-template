# Settings

Edit config (targets, autonomy, Claude, files, appearance) through forms with a save bar.

## Sub-features

- `settings-nav` nav `aria-label="Settings sections"` (General, Files, Appearance, App, Claude, Résumé, Targets, ...; system pages under Advanced).
- `settings-edit` change a field, save via the save bar, value persists in `config/*.yaml`.

## How to get to it (user POV)

- Sidebar `Settings`, or `/settings/<section>`.

## Driving it (user mode, Playwright)

Preconditions: baseline from `README.md`.

- **Open.** `page.goto("./settings/targets")`; role navigation "Settings sections"; heading `Settings`.
- **Edit.** Change one field, press Save in the save bar, reload: value persists; `git diff --no-index examples/config config` or `rg` the key in `config/targets.yaml`. Not yet proven.
- **Proof.** Page text before/after + the YAML line.

## Driving it (dev mode, API)

`curl -s 127.0.0.1:8799/api/settings/...` (routes: `src/careeros/ui/`); then `rg` the key in `config/targets.yaml`.

## UX checks

- One save action; save bar appears on change and says saved.
- Unsaved change warns before leaving (errors prevented).
- Invalid value shows a fix next to the field.
- Section names match user words; few choices per screen.

## Gotchas

- Edits write the checkout's `config/`; cleanup deletes it.
- Section ids come from `src/careeros/ui/settings_schema/sections.py`.
