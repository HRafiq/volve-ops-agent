"""Scoring for cause attribution, implementing docs/eval_protocol.md section 14.5.

Four conditions, all of which must hold. Three of them exist because of specific ways an
earlier version of the protocol could have been passed without the system being any good:

- a macro average over eleven classes at 120 to 150 events moves several points when one
  rare-class event changes, so the margin has to survive resampling rather than merely exist;
- a class absent from the sample is not scored zero, because that measures the sampling;
- abstention without a coverage floor is passed by abstaining on everything but the single
  most confident event.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

from volve_ops.extraction.npt import CauseLabel

# Section 14.5.
RELATIVE_MARGIN: Final[float] = 0.20
MIN_CLASS_INSTANCES: Final[int] = 5
MIN_ATTRIBUTION_COVERAGE: Final[float] = 0.60
ABSTENTION_PRECISION_MARGIN: Final[float] = 0.10
BOOTSTRAP_SAMPLES: Final[int] = 2000
BOOTSTRAP_SEED: Final[int] = 20261006


class LabelledEvent(BaseModel):
    """One hand-labelled event: what the labeller recorded, per docs/labelling_guide.md."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    cause: CauseLabel
    evidence_span: str | None = None
    comment: str = ""


class ClassScore(BaseModel):
    """Per-class precision, recall and F1, with the support that produced them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: CauseLabel
    support: int
    precision: float
    recall: float
    f1: float
    in_macro_average: bool


class MacroScore(BaseModel):
    """A macro F1 and the classes it was taken over."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    macro_f1: float
    classes_in_average: int
    per_class: tuple[ClassScore, ...]

    @property
    def excluded(self) -> tuple[ClassScore, ...]:
        return tuple(c for c in self.per_class if not c.in_macro_average)


def score_macro(
    gold: Sequence[CauseLabel],
    predicted: Sequence[CauseLabel],
    *,
    min_instances: int = MIN_CLASS_INSTANCES,
) -> MacroScore:
    """Macro F1 over classes with enough support to mean anything.

    A class with fewer than `min_instances` true instances is scored and reported but kept out
    of the average, and a class with none is not scored zero: an unobserved class says something
    about the sample, not about the system.
    """
    if len(gold) != len(predicted):
        raise ValueError("gold and predicted must be the same length")

    rows: list[ClassScore] = []
    for label in CauseLabel:
        support = sum(1 for g in gold if g is label)
        if support == 0:
            continue
        true_positive = sum(
            1 for g, p in zip(gold, predicted, strict=True) if g is label and p is label
        )
        predicted_positive = sum(1 for p in predicted if p is label)
        precision = true_positive / predicted_positive if predicted_positive else 0.0
        recall = true_positive / support
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        rows.append(
            ClassScore(
                label=label,
                support=support,
                precision=precision,
                recall=recall,
                f1=f1,
                in_macro_average=support >= min_instances,
            )
        )

    counted = [r for r in rows if r.in_macro_average]
    macro = sum(r.f1 for r in counted) / len(counted) if counted else 0.0
    return MacroScore(macro_f1=macro, classes_in_average=len(counted), per_class=tuple(rows))


def bootstrap_margin(
    gold: Sequence[CauseLabel],
    candidate: Sequence[CauseLabel],
    baseline: Sequence[CauseLabel],
    *,
    samples: int = BOOTSTRAP_SAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    """A 95 percent interval for the candidate's macro-F1 advantage over the baseline.

    Resampling the labelled events, because the question is whether the margin would survive a
    different draw of the same size, which is exactly what a different labelling run would be.
    The seed is fixed so the interval is reproducible rather than a number that moves each time
    it is quoted.
    """
    rng = random.Random(seed)
    size = len(gold)
    differences: list[float] = []
    for _ in range(samples):
        picks = [rng.randrange(size) for _ in range(size)]
        g = [gold[i] for i in picks]
        differences.append(
            score_macro(g, [candidate[i] for i in picks]).macro_f1
            - score_macro(g, [baseline[i] for i in picks]).macro_f1
        )
    differences.sort()
    low = differences[int(0.025 * samples)]
    high = differences[min(samples - 1, int(0.975 * samples))]
    return low, high


class ConditionResult(BaseModel):
    """One of section 14.5's four conditions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    passed: bool
    detail: str


def condition_relative_margin(
    gold: Sequence[CauseLabel],
    candidate: Sequence[CauseLabel],
    baselines: Mapping[str, Sequence[CauseLabel]],
) -> tuple[ConditionResult, str]:
    """Macro F1 at least 20 percent above the better baseline. Returns the baseline it beat."""
    scores = {name: score_macro(gold, p).macro_f1 for name, p in baselines.items()}
    best_name = max(scores, key=lambda k: scores[k])
    best = scores[best_name]
    own = score_macro(gold, candidate).macro_f1
    improvement = (own - best) / best if best > 0 else float("inf") if own > 0 else 0.0
    detail = (
        f"candidate {own:.4f} vs best baseline {best_name} {best:.4f}, {improvement:+.1%}"
        + "; ".join(f" {n}={s:.4f}" for n, s in sorted(scores.items()))
    )
    return (
        ConditionResult(
            name="relative macro-F1 margin",
            passed=improvement >= RELATIVE_MARGIN,
            detail=detail,
        ),
        best_name,
    )


def condition_margin_survives_resampling(
    gold: Sequence[CauseLabel],
    candidate: Sequence[CauseLabel],
    baseline: Sequence[CauseLabel],
) -> ConditionResult:
    """The 95 percent bootstrap interval for the advantage excludes zero."""
    low, high = bootstrap_margin(gold, candidate, baseline)
    return ConditionResult(
        name="margin survives resampling",
        passed=low > 0.0,
        detail=f"95% interval for the advantage: [{low:+.4f}, {high:+.4f}]",
    )


def condition_spans_are_verbatim(
    events: Sequence[LabelledEvent], spans: Mapping[str, str | None]
) -> ConditionResult:
    """Every cited span is a verbatim substring of the comment it cites. A hard gate."""
    failures: list[str] = []
    checked = 0
    for event in events:
        span = spans.get(event.event_id)
        if span is None:
            continue
        checked += 1
        if span not in event.comment:
            failures.append(event.event_id)
    return ConditionResult(
        name="evidence spans verbatim",
        passed=not failures and checked > 0,
        detail=(
            f"{checked - len(failures)}/{checked} spans found verbatim"
            + (f"; fabricated: {failures[:5]}" if failures else "")
        ),
    )


def condition_abstention(
    gold: Sequence[CauseLabel],
    candidate: Sequence[CauseLabel],
    forced: Sequence[CauseLabel],
) -> ConditionResult:
    """Abstention is available, used widely enough to matter, and earns its place.

    `forced` is the same approach with `not_stated` struck from its permitted outputs, which is
    what makes the comparison a statement about abstention rather than about the model.
    """
    attributable = [i for i, g in enumerate(gold) if g is not CauseLabel.NOT_STATED]
    if not attributable:
        return ConditionResult(
            name="abstention", passed=False, detail="no event in the sample has a stated cause"
        )

    attributed = [i for i in attributable if candidate[i] is not CauseLabel.NOT_STATED]
    coverage = len(attributed) / len(attributable)

    def precision(indices: Sequence[int], predictions: Sequence[CauseLabel]) -> float:
        picked = [i for i in indices if predictions[i] is not CauseLabel.NOT_STATED]
        if not picked:
            return 0.0
        return sum(1 for i in picked if predictions[i] is gold[i]) / len(picked)

    selective = precision(range(len(gold)), candidate)
    forced_precision = precision(range(len(gold)), forced)
    margin = selective - forced_precision

    return ConditionResult(
        name="abstention",
        passed=coverage >= MIN_ATTRIBUTION_COVERAGE and margin >= ABSTENTION_PRECISION_MARGIN,
        detail=(
            f"coverage {coverage:.0%} of stated-cause events "
            f"(floor {MIN_ATTRIBUTION_COVERAGE:.0%}); "
            f"precision when attributing {selective:.3f} vs forced {forced_precision:.3f}, "
            f"margin {margin:+.3f} (floor {ABSTENTION_PRECISION_MARGIN:+.2f})"
        ),
    )


def evaluate(
    labelled: Sequence[LabelledEvent],
    candidate: Callable[[str], CauseLabel],
    forced: Callable[[str], CauseLabel],
    spans: Mapping[str, str | None],
    baselines: Mapping[str, Callable[[str], CauseLabel]],
) -> list[ConditionResult]:
    """Run all four conditions. An approach is selected only if every one passes."""
    gold = [e.cause for e in labelled]
    predicted = [candidate(e.event_id) for e in labelled]
    forced_predicted = [forced(e.event_id) for e in labelled]
    baseline_predictions = {
        name: [fn(e.event_id) for e in labelled] for name, fn in baselines.items()
    }

    margin, best_name = condition_relative_margin(gold, predicted, baseline_predictions)
    return [
        margin,
        condition_margin_survives_resampling(gold, predicted, baseline_predictions[best_name]),
        condition_spans_are_verbatim(labelled, spans),
        condition_abstention(gold, predicted, forced_predicted),
    ]
