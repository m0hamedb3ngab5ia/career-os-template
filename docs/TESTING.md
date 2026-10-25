# Testing (TDD), required for every code PR
- Red → green → refactor. Failing test first, same PR as fix/feature. Bug fix = repro test first.
- Unit tests (`@pytest.mark.unit`, pure, fakes for IO) always; integration (`@pytest.mark.integration`, `tests/integration/`) when crossing a boundary: CLI via subprocess on temp repo root, scout → store → tracker with recorded HTTP fixtures, render.py → real PDF, qa over full job dir, applier vs `examples/profile/`.
- Tests read only repo (`examples/`, `tests/fixtures/`) + tmp; never `profile/`, `config/`, `data/`, `$HOME` (CI has none). No network (recorded fixtures). LaTeX tests `skipif` no engine.
- Exempt: SKILL.md-only / docs-only PRs. Python a skill calls is not exempt.
- Run: `.venv/bin/python -m pytest -q` (all), `-m unit`, `-m integration`. CI runs both unit and integration on every PR. Parallel (`-n auto` in addopts); one test / debugger: `.venv/bin/python -m pytest -n0 tests/x.py::t`. While coding: touched tests only (path / `-k`).
- Before pushing code PR: full `pytest -q` locally; CI full suite is gate. Never `gh pr merge --auto` before `/review` is clean (`None.` or findings accepted); merging is the lead's call, not a builder agent's. Before merging private sync PR: full `pytest -q` locally.
- CI shards PR runs (`CAREEROS_TEST_SHARD`/`CAREEROS_TEST_SHARDS`, hash of node ID, `tests/conftest.py`); required `pytest` check aggregates. Reproduce a shard locally with same env vars.
