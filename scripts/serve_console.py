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

Run it behind a real reverse proxy and you want the opposite: uvicorn configured with the proxy's
address in `forwarded_allow_ips`, so the rewrite is trustworthy. That is a deployment decision and
this script does not make it.
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
    parser.add_argument(
        "--trust-proxy-headers",
        action="store_true",
        help=(
            "trust X-Forwarded-For from the configured hops. Only behind a reverse proxy you "
            "control; on loopback it makes the request bound keyable by any caller."
        ),
    )
    args = parser.parse_args(argv)

    from api.main import app

    if not args.trust_proxy_headers:
        print("proxy headers: not trusted; the peer address is the peer address")
    else:
        print("proxy headers: TRUSTED. Only correct behind a reverse proxy you control.")
    print(f"serving      http://{args.host}:{args.port}/")

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        proxy_headers=args.trust_proxy_headers,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
