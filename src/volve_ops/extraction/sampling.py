"""Drawing the sample a human labels, per docs/labelling_guide.md.

Random and stratified, not chosen. Picking interesting comments to label produces a benchmark
of interesting comments, and a system scored on it looks better than it is on the corpus it
will actually meet.

The draw is seeded and reproducible, so the sample can be regenerated and checked rather than
taken on trust, and so a second person can confirm the events were not reselected after seeing
how the first draw scored.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

from volve_ops.extraction.npt import NPTEvent

# docs/eval_protocol.md section 16 fixes the hold-out wells by a rule; this is that rule's result.
HOLD_OUT_WELLS: Final[frozenset[str]] = frozenset({"15/9-F-4", "15/9-F-5", "15/9-F-7", "15/9-F-9"})

# Section 16 again: labels and prompts use pre-boundary reports on development wells only.
PRODUCTION_BOUNDARY_ISO: Final[str] = "2014-07-25"

DEVELOPMENT_TARGET: Final[int] = 135  # the guide's 120 to 150, at its midpoint
HOLD_OUT_TARGET: Final[int] = 60
SAMPLE_SEED: Final[int] = 20261006


class SampleManifest(BaseModel):
    """What was drawn, and under which rule, so the draw can be reproduced and checked."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    split: str
    seed: int
    target: int
    drawn: int
    eligible: int
    event_ids: tuple[str, ...]
    per_subcategory: dict[str, int]


def is_development(event: NPTEvent) -> bool:
    """A development event: not a hold-out well, and not after the production boundary.

    The date restriction exists because the development wells include reports postdating the
    production hold-out boundary, on wells whose production hold-out is scored. Labelling causes
    from one of those means reading narrative about a period the production detector is scored
    on, and a label is not profiling.
    """
    return event.well not in HOLD_OUT_WELLS and str(event.report_date) < PRODUCTION_BOUNDARY_ISO


def is_hold_out(event: NPTEvent) -> bool:
    return event.well in HOLD_OUT_WELLS


def draw_sample(
    events: Sequence[NPTEvent],
    *,
    split: str = "development",
    target: int | None = None,
    seed: int = SAMPLE_SEED,
) -> SampleManifest:
    """Draw a stratified random sample for labelling.

    Stratified by activity subcategory so that rare subcategories appear at all. Without it a
    proportional draw would give `well control`, 29 events in the whole corpus, a good chance of
    appearing zero times, and the taxonomy class it maps to would then be unscoreable.
    """
    if split == "development":
        eligible = [e for e in events if is_development(e)]
        size = target if target is not None else DEVELOPMENT_TARGET
    elif split == "hold-out":
        eligible = [e for e in events if is_hold_out(e)]
        size = target if target is not None else HOLD_OUT_TARGET
    else:
        raise ValueError(f"unknown split {split!r}; expected 'development' or 'hold-out'")

    by_subcategory: dict[str, list[NPTEvent]] = defaultdict(list)
    for event in eligible:
        by_subcategory[event.subcategory or "(none)"].append(event)

    rng = random.Random(seed)
    strata = sorted(by_subcategory)
    # One pass per stratum in round-robin, so a small stratum is exhausted rather than swamped,
    # and the remainder goes to the larger ones.
    pools = {k: rng.sample(by_subcategory[k], len(by_subcategory[k])) for k in strata}
    drawn: list[NPTEvent] = []
    while len(drawn) < size and any(pools.values()):
        for key in strata:
            if not pools[key]:
                continue
            drawn.append(pools[key].pop())
            if len(drawn) >= size:
                break

    drawn.sort(key=lambda e: e.event_id)
    counts: dict[str, int] = defaultdict(int)
    for event in drawn:
        counts[event.subcategory or "(none)"] += 1

    return SampleManifest(
        split=split,
        seed=seed,
        target=size,
        drawn=len(drawn),
        eligible=len(eligible),
        event_ids=tuple(e.event_id for e in drawn),
        per_subcategory=dict(sorted(counts.items())),
    )
