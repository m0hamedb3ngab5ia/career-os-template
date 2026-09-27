"""Map the services' refusals to HTTP: unknown thing -> 404, can't run right now (busy, paused, not set up, not
macOS) -> 409 with the plain-language reason. A job
locked by a run (JobLocked) -> 409 is handled app-wide in app.py, like ValueError -> 400. ValueError -> 400 is handled app-wide in app.py."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from fastapi import HTTPException


@contextmanager
def refusals() -> Iterator[None]:
    from careeros.ui.services.desktop import Unsupported
    from careeros.ui.services.runs import Busy, NotSetUp, Paused

    try:
        yield
    except LookupError as e:
        raise HTTPException(404, str(e).strip("'\"")) from None
    except (Busy, Paused, NotSetUp, Unsupported) as e:
        raise HTTPException(409, str(e)) from None
