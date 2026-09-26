from __future__ import annotations

import html
import re
import time
from abc import ABC, abstractmethod
from typing import Any

import requests

from careeros.models import Posting

USER_AGENT = "careeros/0.1 (job-search automation)"
TIMEOUT = 20

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_RE = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6]|tr|section|table)[^>]*>", re.I)
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NL_RE = re.compile(r"\n{3,}")


class BoardNotFound(Exception):
    pass


class FetchError(Exception):
    pass


def html_to_text(raw: str | None) -> str:
    if not raw:
        return ""
    s = html.unescape(raw)
    if "<" in s and ">" in s:
        s = html.unescape(s)
    s = _BLOCK_RE.sub("\n", s)
    s = _TAG_RE.sub("", s)
    s = html.unescape(s)
    s = _WS_RE.sub(" ", s)
    s = "\n".join(line.strip() for line in s.split("\n"))
    s = _NL_RE.sub("\n\n", s)
    return s.strip()


def get_json(url: str, params: dict[str, Any] | None = None, retries: int = 1) -> Any:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
            if r.status_code == 404:
                raise BoardNotFound(url)
            r.raise_for_status()
            return r.json()
        except BoardNotFound:
            raise
        except (requests.RequestException, ValueError) as e:
            last = e
            if attempt < retries:
                time.sleep(1.5)
    raise FetchError(f"{url}: {last}")


def guess_remote(*fields: str | None) -> bool | None:
    text = " ".join(f for f in fields if f).lower()
    if not text:
        return None
    return "remote" in text


class Adapter(ABC):
    ats: str = ""

    @staticmethod
    def with_close_date(postings: list[Posting]) -> list[Posting]:
        """Fill `closes_at` (YYYY-MM-DD) from the ATS field or the description text, when stated."""
        from careeros.company_policy import closes_at_iso

        for p in postings:
            p.closes_at = closes_at_iso(p)
        return postings

    @abstractmethod
    def fetch(self, board: dict[str, Any]) -> list[Posting]:
        ...

    @abstractmethod
    def parse(self, data: Any, board: dict[str, Any]) -> list[Posting]:
        ...
