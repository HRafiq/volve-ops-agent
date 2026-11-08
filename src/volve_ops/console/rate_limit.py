"""A per-client request bound, for protocol section 22.8 and mark 10.

A fixed-window counter keyed by client address, held in this process. Three limits of that are
worth stating plainly rather than discovering later, because a rate limiter that is trusted
further than it goes is worse than none:

**It is per process.** Two workers behind a load balancer each allow the full rate, so the real
ceiling is the limit times the worker count. The console is served by one process, which is why
this is adequate here and would not be behind a scaled deployment.

**It is keyed by the peer address, and a peer address this process cannot vouch for collapses to
one shared bucket.** `X-Forwarded-For` is never read here, because a caller can set it to whatever
it likes and trusting it hands the key to the attacker.

That is not sufficient on its own, and the first version of this module claimed it was. uvicorn
defaults `proxy_headers=True` with `forwarded_allow_ips="127.0.0.1"`, so in the deployment this
project documents — uvicorn on loopback — `ProxyHeadersMiddleware` has already rewritten
`scope["client"]` from the caller's own header before any of this runs. The limiter was then
keying on an attacker-chosen string, and a rotating header took 100 requests out of 100 through a
limit of 60. The claim that the header is not consulted was true of this file and false of the
process.

So `client_key` checks whether the address it was handed looks like one that arrived in a
forwarded header, and if it does, every such caller shares a single bucket. That is the "fails
closed, throttling everyone rather than nobody" the module claimed from the start and did not do.
The deployment note still matters: run with `--no-proxy-headers` unless a trusted proxy is really
in front, which is what `scripts/serve_console.py` does.

**A fixed window admits a burst at the boundary.** Up to twice the limit can arrive across two
adjacent windows. A sliding window would not, and the extra machinery is not worth it for a
demo bound whose purpose is to stop a loop, not to shape traffic precisely.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Final

from volve_ops.console.limits import (
    MAX_ASSET_REQUESTS_PER_MINUTE,
    MAX_REQUESTS_PER_MINUTE,
    RATE_WINDOW_SECONDS,
)

#: The address used when a request arrives with no peer, which happens in tests.
UNKNOWN_CLIENT: Final[str] = "unknown"

#: The single bucket every caller shares when the peer address cannot be trusted. One key, so a
#: rotating forwarded header buys nothing: the limit applies to all of them together.
FORWARDED_CLIENT: Final[str] = "forwarded-untrusted"


#: Headers that can carry a client address a caller chose. The presence of any of them means this
#: process cannot vouch for the peer it was handed.
FORWARDING_HEADERS: Final[tuple[str, ...]] = (
    "x-forwarded-for",
    "x-real-ip",
    "forwarded",
    "x-client-ip",
    "x-cluster-client-ip",
    "true-client-ip",
    "cf-connecting-ip",
)


def client_key(peer: str | None, forwarding_headers_present: bool) -> str:
    """The bucket key for one request, refusing to trust an address a caller may have chosen.

    `peer` is `request.client.host`, which a proxy-headers middleware may already have replaced
    with a value out of a header. **The rule is presence, not matching**: if any forwarding header
    is on the request, everything in that position shares one bucket.

    The first version tried to detect the rewrite instead, by asking whether the peer appeared in
    the hop list of `X-Forwarded-For`. That closed the attack it was written for and not the next
    one. uvicorn's `ProxyHeadersMiddleware` builds `dict(scope["headers"])`, which keeps the
    **last** of two header lines with the same name; Starlette's `headers.get` returns the
    **first**. So two `X-Forwarded-For` lines put the peer uvicorn installed outside the hop set
    the application read, the match failed, and the attacker's rotating string became the key: 300
    requests out of 300 through a limit of 60.

    Matching is a parsing problem with a long tail — comma forms, ports, IPv6 brackets, duplicate
    lines, RFC 7239's `Forwarded`, and whatever the next middleware does. Presence is one boolean
    and has no tail. The cost is the documented one: behind a real proxy every client shares a
    bucket, which throttles everyone rather than nobody, and `scripts/serve_console.py` runs
    uvicorn with proxy headers off so the peer is the peer.
    """
    if forwarding_headers_present:
        return FORWARDED_CLIENT
    return peer or UNKNOWN_CLIENT


def forwarding_header_present(header_names: Iterable[str]) -> bool:
    """Whether any header on the request can carry a caller-chosen address."""
    lowered = {name.lower() for name in header_names}
    return any(name in lowered for name in FORWARDING_HEADERS)


@dataclass
class FixedWindowLimiter:
    """Counts requests per client per window, and refuses over the limit.

    One entry per client, holding that client's current window and its count. The first version
    keyed on `(client, window)` and swept for stale keys by scanning the **whole** map on every
    request, deleting only the current client's old entries. A client that made one request and
    left kept its key for ever, and the per-request cost grew linearly with every address ever
    seen: 12 microseconds at a thousand clients, 235 at twenty thousand.

    That made the middleware the amplifier the bound exists to prevent. A caller cannot exhaust
    its own rate, but a million distinct source addresses would have every request paying
    milliseconds of CPU before routing, and the map would never shrink.
    """

    limit: int = MAX_REQUESTS_PER_MINUTE
    window_seconds: int = RATE_WINDOW_SECONDS
    max_tracked_clients: int = 100_000
    _state: dict[str, tuple[int, int]] = field(default_factory=dict)
    _last_sweep_window: int = -1

    def _window(self, now: float) -> int:
        return int(now // self.window_seconds)

    def check(self, client: str, *, now: float | None = None) -> tuple[bool, int]:
        """Record one request. Returns whether it is allowed and how many remain."""
        moment = time.monotonic() if now is None else now
        window = self._window(moment)
        stored_window, count = self._state.get(client, (window, 0))
        used = count + 1 if stored_window == window else 1

        # Growth across windows is bounded by sweeping entries from a window that has passed.
        # Within one window the map still holds an entry per distinct caller seen in it, which is
        # the real ceiling and is stated rather than implied.
        #
        # **Once per window, not once per request at the cap.** The first version swept whenever
        # a new client arrived and the map was full, which during a flood of distinct addresses
        # in one window is every request, scanning a full map that has nothing stale in it. That
        # measured 1.5 ms per new client at the default cap — worse than the implementation it
        # replaced, in exactly the case its own docstring gave as the reason for replacing it.
        if (
            client not in self._state
            and len(self._state) >= self.max_tracked_clients
            and self._last_sweep_window != window
        ):
            self._last_sweep_window = window
            self._evict_stale(window)

        self._state[client] = (window, used)
        return used <= self.limit, max(0, self.limit - used)

    def _evict_stale(self, window: int) -> None:
        for client in [c for c, (w, _) in self._state.items() if w != window]:
            del self._state[client]

    def retry_after(self, *, now: float | None = None) -> int:
        """Seconds until the current window ends."""
        moment = time.monotonic() if now is None else now
        return max(1, int(self.window_seconds - (moment % self.window_seconds)))

    def tracked_clients(self) -> int:
        """How many clients the limiter is holding state for. Published so the cap is checkable."""
        return len(self._state)

    def reset(self) -> None:
        self._state.clear()
        self._last_sweep_window = -1


#: The two buckets. Assets get a higher rate because one page load fetches several files.
API_LIMITER: Final[FixedWindowLimiter] = FixedWindowLimiter(limit=MAX_REQUESTS_PER_MINUTE)
ASSET_LIMITER: Final[FixedWindowLimiter] = FixedWindowLimiter(limit=MAX_ASSET_REQUESTS_PER_MINUTE)


def limiter_for(path: str) -> FixedWindowLimiter:
    return API_LIMITER if path.startswith("/api/") else ASSET_LIMITER
