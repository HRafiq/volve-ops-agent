"""The request bound against a real server, because TestClient cannot falsify it.

`tests/test_api_security.py` asserts that `X-Forwarded-For` is not trusted and passes, because
`TestClient` calls the ASGI app directly and never runs uvicorn's `ProxyHeadersMiddleware`. On a
real server that middleware sits **outside** this application and, with uvicorn's default
`proxy_headers=True` and `forwarded_allow_ips="127.0.0.1"`, rewrites `scope["client"]` from the
caller's own header before any application code runs. A rotating header then took 100 requests
out of 100 through a limit of 60.

So the claim was true of the module and false of the process, and the test that asserted it ran in
the one environment where it could not fail. This project committed a lesson about exactly that
after Phase 6 and repeated it here.

These tests start uvicorn the way the README documents and drive it over HTTP.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="the console API is an optional extra")
pytest.importorskip("uvicorn", reason="this test needs a real server, not a test client")

import httpx  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@pytest.fixture
def server() -> Iterator[str]:
    """uvicorn, started exactly as the README documents it, with its own defaults.

    Per test, not per module. The limiter is process state, so a second test sharing a server
    runs against an allowance the first already spent, and `allowed <= limit` then holds however
    broken the limiter is. The bypass test in particular passed that way while a fresh server
    with the bypass restored let 120 of 120 through.
    """
    port = _free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{base}/api/health", timeout=0.5).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:  # pragma: no cover - the server never came up
            pytest.skip("uvicorn did not start")
        yield base
    finally:
        process.terminate()
        process.wait(timeout=10)


class TestTheBoundHoldsOverRealHttp:
    def test_a_plain_caller_is_limited(self, server: str) -> None:
        from volve_ops.console.limits import MAX_REQUESTS_PER_MINUTE

        with httpx.Client(base_url=server, timeout=5.0) as client:
            codes = [
                client.get("/api/health").status_code for _ in range(MAX_REQUESTS_PER_MINUTE + 10)
            ]
        assert codes.count(200) <= MAX_REQUESTS_PER_MINUTE
        assert 429 in codes

    def test_a_rotating_forwarded_header_does_not_buy_more_requests(self, server: str) -> None:
        """The test that could not fail under TestClient, run where it can.

        Every request carries a different `X-Forwarded-For`. Under uvicorn's defaults the peer
        address this process sees is whatever the header said, so if the limiter keyed on it
        directly the caller would get a fresh allowance every time.
        """
        from volve_ops.console.limits import MAX_REQUESTS_PER_MINUTE

        with httpx.Client(base_url=server, timeout=5.0) as client:
            allowed = sum(
                client.get(
                    "/api/health", headers={"X-Forwarded-For": f"10.{index // 250}.{index % 250}.7"}
                ).status_code
                == 200
                for index in range(MAX_REQUESTS_PER_MINUTE * 2)
            )
        assert allowed <= MAX_REQUESTS_PER_MINUTE, (
            f"{allowed} requests allowed through a limit of {MAX_REQUESTS_PER_MINUTE} by rotating "
            "a header the caller controls"
        )

    def test_duplicate_header_lines_do_not_buy_more_requests(self, server: str) -> None:
        """The attack the first repair did not close.

        uvicorn's `ProxyHeadersMiddleware` builds `dict(scope["headers"])`, which keeps the last
        of two lines with the same name; Starlette's `headers.get` returns the first. So two
        `X-Forwarded-For` lines put the peer uvicorn installed outside the hop set the application
        read, a repair that matched one against the other failed to fire, and 300 requests out of
        300 went through a limit of 60.
        """
        from volve_ops.console.limits import MAX_REQUESTS_PER_MINUTE

        allowed = 0
        with httpx.Client(base_url=server, timeout=5.0) as client:
            for index in range(MAX_REQUESTS_PER_MINUTE * 3):
                request = httpx.Request(
                    "GET",
                    f"{server}/api/health",
                    headers=[
                        (b"x-forwarded-for", b"1.1.1.1"),
                        (b"x-forwarded-for", f"10.0.{index // 250}.{index % 250}".encode()),
                    ],
                )
                allowed += client.send(request).status_code == 200
        assert allowed <= MAX_REQUESTS_PER_MINUTE, (
            f"{allowed} allowed through a limit of {MAX_REQUESTS_PER_MINUTE} by sending two "
            "X-Forwarded-For header lines"
        )

    @pytest.mark.parametrize(
        "header", ["X-Real-IP", "Forwarded", "CF-Connecting-IP", "True-Client-IP"]
    )
    def test_other_forwarding_headers_do_not_buy_more_requests(
        self, server: str, header: str
    ) -> None:
        """Presence, not matching, is the rule, so the whole family is covered by one test shape."""
        from volve_ops.console.limits import MAX_REQUESTS_PER_MINUTE

        with httpx.Client(base_url=server, timeout=5.0) as client:
            allowed = sum(
                client.get("/api/health", headers={header: f"10.9.{index % 250}.4"}).status_code
                == 200
                for index in range(MAX_REQUESTS_PER_MINUTE * 2)
            )
        assert allowed <= MAX_REQUESTS_PER_MINUTE
