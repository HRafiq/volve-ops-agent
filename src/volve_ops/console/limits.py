"""The bounds of protocol section 22.8, declared in one place.

Fixed in the protocol before they were implemented, so none of them is a number chosen after
seeing what the system happened to do. The health tab reads them from here rather than printing
its own copy, because a screen that states a limit it does not share with the code is a figure
from nowhere.

**What is not here, and why.** The design brief asks for model-call budgets alongside rate
limits. No shipped module calls a model, so a token budget would count nothing and a cost curve
denominated in tokens would be a decorative zero. It is declared not applicable rather than
implemented as a counter that never moves, which is the same discipline section 22.1 applies to
the three vacuous injection invariants.

What is real here is compute and storage. A review note is appended to a log that is append-only
by design, so an unbounded note is unbounded permanently: there is no route that removes one.
"""

from __future__ import annotations

from typing import Final

#: Characters in a review note. Long enough for a paragraph of reasoning about a finding, which
#: is what the field is for, and short enough that a log cannot be grown without limit by someone
#: holding the key down.
MAX_NOTE_CHARS: Final[int] = 4_000

#: Characters in an actor name.
MAX_ACTOR_CHARS: Final[int] = 200

#: Requests per minute per client against the API.
MAX_REQUESTS_PER_MINUTE: Final[int] = 60

#: Requests per minute per client against the built console's static assets. Higher because one
#: page load fetches several files and a reader moving between screens should not be throttled.
MAX_ASSET_REQUESTS_PER_MINUTE: Final[int] = 120

#: The window the two rates are measured over.
RATE_WINDOW_SECONDS: Final[int] = 60

#: Protections the design brief asks for that have nothing to protect in this architecture.
#: Carried as data so the health tab can render the reason rather than leaving a blank row.
NOT_APPLICABLE: Final[dict[str, str]] = {
    "model_call_budget": (
        "No shipped module calls a language model, so there are no model calls to budget and no "
        "token spend to cap. A counter here would report zero for ever and read as a protection."
    ),
    "api_key_rotation": (
        "The console holds no third-party credential: it reads run manifests from disk and calls "
        "nothing outbound. There is no key whose rotation would protect anything."
    ),
}


def declared_limits() -> dict[str, int]:
    """Every enforced bound, for the health tab and for the test that checks it is enforced."""
    return {
        "max_note_chars": MAX_NOTE_CHARS,
        "max_actor_chars": MAX_ACTOR_CHARS,
        "max_requests_per_minute": MAX_REQUESTS_PER_MINUTE,
        "max_asset_requests_per_minute": MAX_ASSET_REQUESTS_PER_MINUTE,
        "rate_window_seconds": RATE_WINDOW_SECONDS,
    }
