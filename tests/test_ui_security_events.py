"""careeros.ui.security (loopback Host/Origin, the X-CareerOS header on writes) and careeros.ui.events (SSE)."""
from __future__ import annotations

import asyncio
import json

import pytest

from careeros.ui.events import Broker, format_sse
from careeros.ui.security import LOOPBACK, check_request, is_loopback_host

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("host,ok", [
    ("127.0.0.1", True), ("localhost", True), ("::1", True), ("0.0.0.0", False), ("192.168.1.4", False),
    ("example.com", False), ("", False),
])
def test_is_loopback_host(host, ok):
    assert is_loopback_host(host) is ok


def _h(**kw):
    return {k.replace("_", "-"): v for k, v in kw.items()}


@pytest.mark.parametrize("method,headers,expect", [
    ("GET", _h(host="127.0.0.1:8765"), None),
    ("GET", _h(host="localhost:8765"), None),
    ("GET", _h(host="[::1]:8765"), None),
    ("GET", _h(host="evil.example:8765"), 421),                  # DNS rebinding: a foreign name for our port
    ("GET", _h(), 421),
    ("GET", _h(host="127.0.0.1:8765", origin="http://127.0.0.1:8765"), None),
    ("GET", _h(host="127.0.0.1:8765", origin="https://evil.example"), 403),
    ("GET", _h(host="127.0.0.1:8765", origin="null"), 403),
    ("POST", _h(host="127.0.0.1:8765"), 403),                     # writes need the header
    ("POST", _h(host="127.0.0.1:8765", x_careeros="1"), None),
    ("DELETE", _h(host="127.0.0.1:8765", x_careeros="0"), 403),
    ("PUT", _h(host="127.0.0.1:8765", x_careeros="1", origin="http://evil.example"), 403),
    ("HEAD", _h(host="127.0.0.1"), None),
    ("OPTIONS", _h(host="127.0.0.1"), None),
])
def test_check_request(method, headers, expect):
    got = check_request(method, headers, LOOPBACK)
    assert (got[0] if got else None) == expect


def test_check_request_accepts_extra_hosts():
    assert check_request("GET", {"host": "testserver"}, LOOPBACK | {"testserver"}) is None


def test_format_sse_one_event():
    out = format_sse("changed", {"jobs": ["a"]}, id="7")
    assert out == 'id: 7\nevent: changed\ndata: {"jobs": ["a"]}\n\n'


def test_format_sse_splits_multiline_data():
    out = format_sse("log", "a\nb")
    assert out == 'event: log\ndata: "a\\nb"\n\n'
    assert json.loads(out.split("data: ", 1)[1]) == "a\nb"


def test_broker_delivers_to_every_subscriber_from_another_thread():
    import threading

    async def main():
        b = Broker()
        q1, q2 = b.subscribe(), b.subscribe()
        t = threading.Thread(target=b.publish, args=("changed", {"n": 1}))
        t.start()
        t.join()
        got = await asyncio.wait_for(asyncio.gather(q1.get(), q2.get()), 2)
        b.unsubscribe(q1)
        b.publish("changed", {"n": 2})
        assert await asyncio.wait_for(q2.get(), 2) == ("changed", {"n": 2}, 2)
        assert q1.empty()
        return got

    got = asyncio.run(main())
    assert got == [("changed", {"n": 1}, 1), ("changed", {"n": 1}, 1)]


def test_broker_drops_oldest_when_a_client_lags():
    async def main():
        b = Broker(maxsize=2)
        q = b.subscribe()
        for i in range(4):
            b.publish("changed", {"n": i})
        await asyncio.sleep(0.05)
        return [q.get_nowait()[1]["n"] for _ in range(q.qsize())]

    assert asyncio.run(main()) == [2, 3]
