"""Drawing the expert adjudication subsample fixed in protocol section 17.4.

Section 17.4 is the route by which the suspended cause-attribution pass marks could be restored:
a reader with drilling-operations experience labels 40 events blind, and agreement of at least 80
percent with the machine labels restores them. This module draws those 40 and nothing else.

Two properties matter more than they look.

The draw is **stratified on the machine label**, half from the three classes the labelling guide
predicts will split two labellers, because a random draw at this size would give those classes two
or three instances between them and the agreement figure would say nothing about the cases it
exists to test.

The worksheet carries **exactly protocol section 14.2's permitted set**: the comment, the activity
code, the state and detail state, and the timestamps. Not the machine label, not its span, not its
applied rule, and not what either baseline predicts.

It also, deliberately, does not carry the wellbore identifier, which the machine labelling pass did
see. That was a deviation from section 14.2 and is disclosed in section 17.5 rather than repeated
here: a wellbore name carries the era, since the `15/9-19` wellbores are 1990s exploration and the
`F-` wellbores are 2000s development, and era plausibly moves a cause label.

Field-level blinding is not the whole of blinding. The adjudicator also reads the labelling guide,
and the guide's conventions section describes how the first pass resolved several of these very
events. Section 17.4 names which version of the guide an adjudicator is given for that reason. This
module cannot enforce that and does not claim to.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

from volve_ops.extraction.npt import CauseLabel, NPTEvent

# Section 17.4 fixes all three. They are here rather than as arguments because a subsample size
# or a seed chosen at run time is a subsample chosen after seeing what it produces.
ADJUDICATION_SIZE: Final[int] = 40
ADJUDICATION_SEED: Final[int] = 20261006

# The three the guide names as the pair-splitting classes. Half the draw comes from these.
CONTESTED: Final[frozenset[CauseLabel]] = frozenset(
    {
        CauseLabel.EQUIPMENT_FAILURE,
        CauseLabel.EQUIPMENT_MAINTENANCE,
        CauseLabel.RIG_SERVICE,
    }
)


class AdjudicationItem(BaseModel):
    """One blind worksheet row. Everything the guide permits a labeller to see, and no more."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    position: int
    event_id: str
    start_time: str
    end_time: str
    duration_hours: float
    activity_code: str
    state: str
    state_detail: str
    comment: str


class AdjudicationDraw(BaseModel):
    """The drawn subsample, with enough about the draw to check it was the specified one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    size: int
    seed: int
    from_contested_classes: int
    from_the_rest: int
    eligible: int
    items: tuple[AdjudicationItem, ...]

    @property
    def event_ids(self) -> tuple[str, ...]:
        return tuple(item.event_id for item in self.items)


def draw_adjudication_sample(
    labels: Mapping[str, CauseLabel],
    events: Sequence[NPTEvent],
    *,
    size: int = ADJUDICATION_SIZE,
    seed: int = ADJUDICATION_SEED,
) -> AdjudicationDraw:
    """Draw section 17.4's 40 events: half contested classes, half at random from the rest.

    `labels` is read only to stratify. It does not reach the worksheet, which is the point of
    separating the draw from what the draw emits.

    Where a stratum is short, the shortfall is taken from the other rather than the draw being
    silently smaller: 40 is the size the protocol fixed, and a draw that quietly returns 31 makes
    the agreement interval wider than the figure it is reported beside implies.
    """
    by_id = {event.event_id: event for event in events}
    missing = sorted(set(labels) - set(by_id))
    if missing:
        raise ValueError(
            f"{len(missing)} labelled events are not in this extraction, starting {missing[:3]}; "
            "the labels and the store have drifted apart"
        )

    contested = sorted(i for i, cause in labels.items() if cause in CONTESTED)
    rest = sorted(i for i, cause in labels.items() if cause not in CONTESTED)
    if size > len(contested) + len(rest):
        raise ValueError(f"cannot draw {size} from {len(contested) + len(rest)} labelled events")

    rng = random.Random(seed)
    half = size // 2
    picked_contested = rng.sample(contested, min(half, len(contested)))
    remaining = size - len(picked_contested)
    picked_rest = rng.sample(rest, min(remaining, len(rest)))
    if len(picked_contested) + len(picked_rest) < size:
        spare = sorted(set(contested) - set(picked_contested))
        picked_contested += rng.sample(spare, size - len(picked_contested) - len(picked_rest))

    chosen = sorted(picked_contested + picked_rest)
    rng.shuffle(chosen)

    items = tuple(
        AdjudicationItem(
            position=position,
            event_id=event_id,
            start_time=by_id[event_id].start_time.isoformat(),
            end_time=by_id[event_id].end_time.isoformat(),
            duration_hours=by_id[event_id].duration_hours,
            activity_code=by_id[event_id].activity_code,
            state=by_id[event_id].state,
            state_detail=by_id[event_id].state_detail,
            comment=by_id[event_id].comment,
        )
        for position, event_id in enumerate(chosen, start=1)
    )
    return AdjudicationDraw(
        size=len(items),
        seed=seed,
        from_contested_classes=len(picked_contested),
        from_the_rest=len(picked_rest),
        eligible=len(labels),
        items=items,
    )


def agreement_rate(
    machine: Mapping[str, CauseLabel], expert: Mapping[str, CauseLabel]
) -> tuple[int, int]:
    """Agreement over the events both cover, which is what section 17.4's threshold is read on."""
    shared = sorted(set(machine) & set(expert))
    return sum(1 for i in shared if machine[i] is expert[i]), len(shared)
