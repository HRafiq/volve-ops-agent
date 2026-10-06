"""Trajectory, stability and cost, per protocol section 19.7.

One of these gates and the rest are reported, which is the honest division: a controller that asks
the same question twice has a defect, and everything else here describes behaviour rather than
judging it.

Stability deserves its own sentence because it is the easiest figure here to oversell. With no model
called, repeating a run reproduces the verdict exactly, every time. That is determinism, not
reliability, and section 19.7 requires it to be reported as such.
"""

from __future__ import annotations

import collections
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from volve_ops.investigation.schemas import Finding
from volve_ops.investigation.trace import Stage, Trace


class RepeatedCall(BaseModel):
    """The same question asked twice in one investigation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    well: str
    episode_onset: str
    judgement_key: str
    value: str
    times: int


class TrajectoryReport(BaseModel):
    """What the traces say about how the investigations ran."""

    # `model_called` collides with pydantic's reserved `model_` prefix. Released rather than
    # renamed: whether a model was called is what decides whether the stability figure means
    # anything, and an awkward synonym would obscure it.
    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    investigations: int
    steps_total: int
    steps_min: int
    steps_max: int
    retrieval_passes: dict[str, int]
    stop_conditions: dict[str, int]
    tokens: int
    cost_usd: float
    repeated_calls: tuple[RepeatedCall, ...] = ()
    verdicts_stable: bool = True
    model_called: bool = False

    @property
    def steps_mean(self) -> float:
        return self.steps_total / self.investigations if self.investigations else 0.0

    @property
    def passed(self) -> bool:
        """Section 19.7's one gate: no repeated identical tool call."""
        return not self.repeated_calls

    @property
    def stability_is_determinism(self) -> bool:
        """Whether the stability figure is a property of the system rather than a result.

        True while no model is called. Section 19.7 asks for this to be said out loud rather than
        letting a reader read 1.0 as reliability.
        """
        return not self.model_called


def assess(
    traces: Sequence[Trace],
    findings: Sequence[Finding],
    *,
    model_called: bool = False,
    verdicts_stable: bool = True,
) -> TrajectoryReport:
    """Summarise a set of runs.

    A repeated call is counted on the retrieval query rather than the step, because two steps that
    differ only in their pass number are not two questions. Asking the same query twice is.
    """
    repeated: list[RepeatedCall] = []
    passes: collections.Counter[str] = collections.Counter()

    for trace in traces:
        queries = [
            str(step.judgement)
            for step in trace.steps
            if step.stage is Stage.RETRIEVE_EVIDENCE and step.judgement is not None
        ]
        passes[str(len(queries))] += 1
        for value, times in collections.Counter(queries).items():
            if times > 1:
                repeated.append(
                    RepeatedCall(
                        well=trace.well,
                        episode_onset=trace.episode_onset,
                        judgement_key="retrieval_query",
                        value=value,
                        times=times,
                    )
                )

    counts = [len(trace.steps) for trace in traces]
    return TrajectoryReport(
        investigations=len(traces),
        steps_total=sum(counts),
        steps_min=min(counts, default=0),
        steps_max=max(counts, default=0),
        retrieval_passes=dict(sorted(passes.items())),
        stop_conditions=dict(
            collections.Counter(f.stop_reason.value for f in findings).most_common()
        ),
        tokens=sum(trace.tokens for trace in traces),
        cost_usd=sum(trace.cost_usd for trace in traces),
        repeated_calls=tuple(repeated),
        verdicts_stable=verdicts_stable,
        model_called=model_called,
    )
