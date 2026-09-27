"""Dump the UI API's OpenAPI schema, deterministically, for the frontend's generated types.

    python -m careeros.ui.openapi > ui/openapi.json       # then: cd ui && npm run gen:api

The schema is built from the routers alone: the app gets a placeholder Settings and index (neither is read while
the schema is built), so no path or config value of this machine can reach the output. Keys are sorted, and a
test checks the committed ui/openapi.json against a fresh dump.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def schema() -> dict[str, Any]:
    from careeros.config import Settings
    from careeros.ui.app import create_app
    from careeros.ui.events import Broker

    app = create_app(Settings(root=Path("/nonexistent")), index=object(), broker=Broker(),  # type: ignore[arg-type]
                     static_dir=Path("/nonexistent"))
    return app.openapi()


def dump() -> str:
    return json.dumps(schema(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    import sys

    sys.stdout.write(dump())
