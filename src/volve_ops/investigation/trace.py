"""The replayable trace, which protocol section 18.7 requires to replay exactly.

A trace that merely logged what happened would not satisfy that pass mark, because replaying it
would mean trusting the log. What is recorded instead is every point at which the model's judgement
entered: the stage, the question put to it, and the answer it gave. Replay re-runs the controller
with those answers substituted for a model, so the finding is recomputed rather than read back.

That has a useful side effect. If the controller has any hidden nondeterminism, an unordered set
iterated into output, a timestamp folded into a field, a seed left unset, then replay produces a
different finding and the pass mark fails. The replay test is therefore a determinism test on the
controller, which is what makes it worth having.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

TRACE_FORMAT_VERSION: Final[str] = "trace-v0"


class Stage(StrEnum):
    """The controller's declared stage sequence, from protocol section 18.1.

    Recorded on every step so that a trace whose stages do not match this sequence is detectable.
    Section 18.1 makes that a defect: it is how the bounded-controller constraint is checked rather
    than asserted.
    """

    VALIDATE_REQUEST = "validate_request"
    LOAD_EXPECTATION = "load_expectation"
    DIAGNOSTIC_BUNDLE = "diagnostic_bundle"
    FORM_HYPOTHESES = "form_hypotheses"
    RETRIEVE_EVIDENCE = "retrieve_evidence"
    SEEK_CONTRADICTION = "seek_contradiction"
    DECIDE_CONTINUE = "decide_continue"
    COMPOSE_FINDING = "compose_finding"
    VALIDATE_PROVENANCE = "validate_provenance"


#: The order the controller runs its stages in. `RETRIEVE_EVIDENCE`, `SEEK_CONTRADICTION` and
#: `DECIDE_CONTINUE` may repeat as a loop; the rest occur once each.
STAGE_SEQUENCE: Final[tuple[Stage, ...]] = (
    Stage.VALIDATE_REQUEST,
    Stage.LOAD_EXPECTATION,
    Stage.DIAGNOSTIC_BUNDLE,
    Stage.FORM_HYPOTHESES,
    Stage.RETRIEVE_EVIDENCE,
    Stage.SEEK_CONTRADICTION,
    Stage.DECIDE_CONTINUE,
    Stage.COMPOSE_FINDING,
    Stage.VALIDATE_PROVENANCE,
)

REPEATABLE: Final[frozenset[Stage]] = frozenset(
    {Stage.RETRIEVE_EVIDENCE, Stage.SEEK_CONTRADICTION, Stage.DECIDE_CONTINUE}
)


class Step(BaseModel):
    """One recorded step. `judgement` is present only where the model was consulted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int
    stage: Stage
    summary: str
    judgement_key: str | None = None
    judgement: Any = None
    tokens: int = 0
    cost_usd: float = 0.0


class Trace(BaseModel):
    """Everything needed to recompute a finding without consulting a model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    format_version: str = TRACE_FORMAT_VERSION
    investigator_version: str
    well: str
    episode_onset: str
    steps: tuple[Step, ...] = ()

    @property
    def stages(self) -> tuple[Stage, ...]:
        return tuple(step.stage for step in self.steps)

    @property
    def tokens(self) -> int:
        return sum(step.tokens for step in self.steps)

    @property
    def cost_usd(self) -> float:
        return sum(step.cost_usd for step in self.steps)

    @property
    def judgements(self) -> dict[str, Any]:
        """The model's answers, keyed so replay can look each one up rather than count steps."""
        return {s.judgement_key: s.judgement for s in self.steps if s.judgement_key is not None}

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2) + "\n", encoding="utf-8")

    @classmethod
    def read(cls, path: Path) -> Trace:
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))


class TraceError(Exception):
    """The trace does not describe a run the controller could have produced."""


def check_stage_order(stages: Sequence[Stage]) -> None:
    """Refuse a stage sequence the declared controller could not have produced.

    This is the bounded-agency check from section 18.1, and it is three rules rather than a clever
    one, because a check nobody can read is not evidence of anything:

    1. A stage that runs once may not repeat.
    2. The once-only stages appear in their declared relative order. They may be absent, since a
       run curtailed by section 18.3 can stop before reaching them.
    3. The loop stages appear only after hypotheses exist and before the finding is composed.

    An unconstrained loop that asked a model what to do next would break rule 2 or rule 3, and both
    are visible from the trace alone without reading the controller.
    """
    if not stages:
        raise TraceError("a trace with no steps records nothing")

    once_only = [s for s in STAGE_SEQUENCE if s not in REPEATABLE]
    seen: list[Stage] = []
    for stage in stages:
        if stage in REPEATABLE:
            continue
        if stage in seen:
            raise TraceError(f"{stage.value} runs once in the declared sequence but repeats here")
        seen.append(stage)
    ordered = [s for s in once_only if s in seen]
    if seen != ordered:
        raise TraceError(
            f"once-only stages are out of order: got {[s.value for s in seen]}, "
            f"declared order is {[s.value for s in once_only]}"
        )

    opened = False
    composed = False
    for stage in stages:
        if stage is Stage.FORM_HYPOTHESES:
            opened = True
        elif stage is Stage.COMPOSE_FINDING:
            composed = True
        elif stage in REPEATABLE:
            if not opened:
                raise TraceError(f"{stage.value} runs before any hypothesis exists")
            if composed:
                raise TraceError(f"{stage.value} runs after the finding was composed")


class TraceRecorder(BaseModel):
    """Collects steps as the controller runs, and totals the budget as it goes."""

    model_config = ConfigDict(extra="forbid")

    investigator_version: str
    well: str
    episode_onset: str
    steps: list[Step] = Field(default_factory=list)

    def record(
        self,
        stage: Stage,
        summary: str,
        *,
        judgement_key: str | None = None,
        judgement: Any = None,
        tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> Step:
        step = Step(
            index=len(self.steps),
            stage=stage,
            summary=summary,
            judgement_key=judgement_key,
            judgement=judgement,
            tokens=tokens,
            cost_usd=cost_usd,
        )
        self.steps.append(step)
        return step

    @property
    def tokens(self) -> int:
        return sum(step.tokens for step in self.steps)

    @property
    def cost_usd(self) -> float:
        return sum(step.cost_usd for step in self.steps)

    def finish(self) -> Trace:
        check_stage_order([step.stage for step in self.steps])
        return Trace(
            investigator_version=self.investigator_version,
            well=self.well,
            episode_onset=self.episode_onset,
            steps=tuple(self.steps),
        )
