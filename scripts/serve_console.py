"""Serve the operator console the way it is meant to be served.

    python scripts/serve_console.py --port 8000

**`proxy_headers=False` is the point of this file.** uvicorn defaults it to `True` with
`forwarded_allow_ips="127.0.0.1"`, so running `python -m uvicorn api.main:app` on loopback puts
`ProxyHeadersMiddleware` outside the application, rewriting the peer address from the caller's own
`X-Forwarded-For` before any of this project's code runs. The request bound of protocol section
22.8 then keys on a string the caller chose, and a rotating header takes any number of requests
through a limit of sixty.

The application defends itself as well: a request carrying any forwarding header is keyed into a
single shared bucket, because a process that cannot vouch for a peer address should throttle
everything in that position together. That is the safe direction and it is a blunt one. With proxy
headers off, the peer is the peer and ordinary callers are limited individually, which is what the
bound is for.

**There is no flag to trust them.** An earlier version had one, and it did nothing it claimed:
the flag controls whether `ProxyHeadersMiddleware` rewrites `scope["client"]`, and the application
now ignores that address whenever a forwarding header is present, so turning the flag on left two
genuinely distinct clients behind the proxy sharing a bucket anyway. A switch whose help text
describes behaviour it does not produce is worse than its absence.

Running behind a real reverse proxy wants a different design, not a flag: the limiter would have
to trust a named hop and key on the address before it, and nothing here measures whether that is
correct for a given proxy. It is recorded as deferred in `SECURITY.md` rather than half-built.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    from api.main import app

    print("proxy headers: not trusted; the peer address is the peer address")
    print(f"serving      http://{args.host}:{args.port}/")

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        proxy_headers=False,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
