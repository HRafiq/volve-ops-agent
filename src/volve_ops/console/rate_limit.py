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
from collections import defaultdict
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
    """Counts requests per client per window, and refuses over the limit."""

    limit: int = MAX_REQUESTS_PER_MINUTE
    window_seconds: int = RATE_WINDOW_SECONDS
    _counts: dict[tuple[str, int], int] = field(default_factory=lambda: defaultdict(int))

    def _window(self, now: float) -> int:
        return int(now // self.window_seconds)

    def check(self, client: str, *, now: float | None = None) -> tuple[bool, int]:
        """Record one request. Returns whether it is allowed and how many remain."""
        moment = time.monotonic() if now is None else now
        window = self._window(moment)
        key = (client, window)
        self._counts[key] += 1
        used = self._counts[key]
        # Old windows are dropped when a new one starts for that client, which keeps the map
        # bounded by the number of distinct clients rather than by time.
        for stale in [k for k in self._counts if k[0] == client and k[1] != window]:
            del self._counts[stale]
        return used <= self.limit, max(0, self.limit - used)

    def retry_after(self, *, now: float | None = None) -> int:
        """Seconds until the current window ends."""
        moment = time.monotonic() if now is None else now
        return max(1, int(self.window_seconds - (moment % self.window_seconds)))

    def reset(self) -> None:
        self._counts.clear()


#: The two buckets. Assets get a higher rate because one page load fetches several files.
API_LIMITER: Final[FixedWindowLimiter] = FixedWindowLimiter(limit=MAX_REQUESTS_PER_MINUTE)
ASSET_LIMITER: Final[FixedWindowLimiter] = FixedWindowLimiter(limit=MAX_ASSET_REQUESTS_PER_MINUTE)


def limiter_for(path: str) -> FixedWindowLimiter:
    return API_LIMITER if path.startswith("/api/") else ASSET_LIMITER
