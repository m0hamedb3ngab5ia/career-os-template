"""Request guard for the local UI server.

The server binds to loopback, but a browser page from any site can still send requests to 127.0.0.1, and a DNS
rebinding attack can make a foreign host name resolve to it. So every request must name a loopback Host, a
browser Origin (when sent) must be a loopback origin, and every write must carry `X-CareerOS: 1`: a header a
cross-site form or image cannot add without a CORS preflight, which this server never grants.
"""
from __future__ import annotations

from typing import Mapping
from urllib.parse import urlsplit

LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
WRITE_HEADER = "x-careeros"


def is_loopback_host(host: str) -> bool:
    return host in LOOPBACK


def _hostname(netloc: str) -> str:
    try:
        return urlsplit(f"//{netloc}").hostname or ""
    except ValueError:
        return ""


def check_request(method: str, headers: Mapping[str, str], allowed_hosts: frozenset[str] | set[str]
                  ) -> tuple[int, str] | None:
    """None when the request may proceed, else (status code, reason). Header names are lower-case."""
    host = _hostname(headers.get("host", ""))
    if host not in allowed_hosts:
        return 421, "this server only answers requests addressed to 127.0.0.1 / localhost"
    origin = headers.get("origin")
    if origin is not None:
        parts = urlsplit(origin) if origin != "null" else None
        if not parts or parts.scheme not in ("http", "https") or (parts.hostname or "") not in allowed_hosts:
            return 403, "cross-origin request refused"
    if method.upper() not in SAFE_METHODS and headers.get(WRITE_HEADER) != "1":
        return 403, "writes need the X-CareerOS: 1 header"
    return None
