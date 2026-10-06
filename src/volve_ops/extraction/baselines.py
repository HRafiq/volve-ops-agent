"""The two cause-attribution baselines, which read nothing.

docs/eval_protocol.md section 14.4 fixes both, including their mapping tables, and section 13
exempts them from amendment. The tables are reproduced here because a baseline whose mapping
lives only in prose is a baseline nobody can run; where this module and the protocol disagree,
the protocol is the specification.

They exist to make a candidate prove it added something. A great many interruptions are caused
by exactly what their code says, and `stateDetailActivity` hands out `equipment failure` on
1,535 blocks for free. A model that reads a comment and does no better than restating a label
it was given has not earned its place in the pipeline.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from volve_ops.extraction.npt import CauseLabel, NPTEvent

# Section 14.4, table one. Exempt from amendment with the baseline it defines.
SUBCATEGORY_TO_CAUSE: Final[dict[str, CauseLabel]] = {
    "repair": CauseLabel.EQUIPMENT_FAILURE,
    "maintain": CauseLabel.EQUIPMENT_MAINTENANCE,
    "waiting on weather": CauseLabel.WAITING_ON_WEATHER,
    "fish": CauseLabel.HOLE_PROBLEM,
    "lost circulation": CauseLabel.HOLE_PROBLEM,
    "sidetrack": CauseLabel.HOLE_PROBLEM,
    "rig up/down": CauseLabel.RIG_SERVICE,
    "well control": CauseLabel.WELL_CONTROL,
    "wait": CauseLabel.NOT_STATED,
    "other": CauseLabel.NOT_STATED,
}

# Section 14.4, table two.
STATE_DETAIL_TO_CAUSE: Final[dict[str, CauseLabel]] = {
    "equipment failure": CauseLabel.EQUIPMENT_FAILURE,
    "stuck equipment": CauseLabel.HOLE_PROBLEM,
    "circulation loss": CauseLabel.HOLE_PROBLEM,
    "mud loss": CauseLabel.HOLE_PROBLEM,
    "operation failed": CauseLabel.NOT_STATED,
    "success": CauseLabel.NOT_STATED,
}


def echo_subcategory(event: NPTEvent) -> CauseLabel:
    """Attribute the cause from the activity subcategory alone."""
    return SUBCATEGORY_TO_CAUSE.get(event.subcategory.strip().lower(), CauseLabel.NOT_STATED)


def echo_state_detail(event: NPTEvent) -> CauseLabel:
    """Attribute the cause from the detail state alone."""
    return STATE_DETAIL_TO_CAUSE.get(event.state_detail.strip().lower(), CauseLabel.NOT_STATED)


BASELINES: Final[dict[str, Callable[[NPTEvent], CauseLabel]]] = {
    "echo-subcategory": echo_subcategory,
    "echo-statedetail": echo_state_detail,
}
