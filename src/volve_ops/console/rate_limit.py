"""A per-client request bound, for protocol section 22.8 and mark 10.

A fixed-window counter keyed by client address, held in this process. Three limits of that are
worth stating plainly rather than discovering later, because a rate limiter that is trusted
further than it goes is worse than none:

**It is per process.** Two workers behind a load balancer each allow the full rate, so the real
ceiling is the limit times the worker count. The console is served by one process, which is why
this is adequate here and would not be behind a scaled deployment.

**It is keyed by the peer address**, and `X-Forwarded-For` is deliberately not consulted. A
caller can set that header to whatever it likes, so trusting it hands the key to the attacker.
Behind a proxy the peer address is the proxy's, and every client shares one bucket: that fails
closed, throttling everyone rather than nobody, and the deployment note has to say so.

**A fixed window admits a burst at the boundary.** Up to twice the limit can arrive across two
adjacent windows. A sliding window would not, and the extra machinery is not worth it for a
demo bound whose purpose is to stop a loop, not to shape traffic precisely.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Final

from volve_ops.console.limits import (
    MAX_ASSET_REQUESTS_PER_MINUTE,
    MAX_REQUESTS_PER_MINUTE,
    RATE_WINDOW_SECONDS,
)

#: The address used when a request arrives with no peer, which happens in tests.
UNKNOWN_CLIENT: Final[str] = "unknown"


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
