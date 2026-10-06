"""Backtest harness for the expectation models.

Evaluation mirrors how the expectation is used, which docs/eval_protocol.md section 8 fixes:
fit on a stable reference window, then carry forward a fixed number of valid producing days
without refitting. Measuring a model that refits every day would measure something the detector
never does, and would flatter any model that tracks noise.

Horizons are 7, 14 and 28 valid producing days, and the conditions must hold at all three. A
model with one-day skill and no multi-week skill is useless to a detector that holds an
expectation across a sustained episode.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from statistics import mean

from pydantic import BaseModel, ConfigDict

from volve_ops.domain.day_class import ClassifiedDay, DayClass
from volve_ops.domain.expectation import CANDIDATE_MODELS, ExpectationModel
from volve_ops.domain.regimes import StableWindow
from volve_ops.domain.stats import clopper_pearson, wape

HORIZONS: tuple[int, ...] = (7, 14, 28)

# Section 8's gates.
RELATIVE_WAPE_IMPROVEMENT = 0.10
LOWER_TAIL_BOUNDS = (0.05, 0.20)
CALIBRATION_MIN_DAYS = 150
BIAS_MIN_DAYS = 60
BIAS_TOLERANCE = 0.05


class EvaluatedDay(BaseModel):
    """One carried-forward prediction against what the well actually did."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    well: str
    horizon: int
    steps_ahead: int
    window_index: int
    actual: float
    predicted: float
    lower: float
    upper: float

    @property
    def below_lower(self) -> bool:
        return self.actual < self.lower

    @property
    def residual(self) -> float:
        return self.actual - self.predicted


class ModelResult(BaseModel):
    """Everything section 8 needs about one candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    model_name: str
    evaluated: tuple[EvaluatedDay, ...]

    def at_horizon(self, horizon: int) -> tuple[EvaluatedDay, ...]:
        return tuple(e for e in self.evaluated if e.horizon == horizon)

    def pooled_wape(self, horizon: int) -> float | None:
        rows = self.at_horizon(horizon)
        if not rows:
            return None
        try:
            return wape([r.actual for r in rows], [r.predicted for r in rows])
        except ValueError:
            return None

    def wells(self) -> tuple[str, ...]:
        return tuple(sorted({e.well for e in self.evaluated}))

    def for_well(self, well: str) -> tuple[EvaluatedDay, ...]:
        return tuple(e for e in self.evaluated if e.well == well)


def _valid_rates(days: Sequence[ClassifiedDay]) -> list[tuple[int, float, float | None]]:
    """Index, rate and choke of each valid producing day, within the well's own sequence.

    The choke travels with the day because an operating-condition-aware model needs the
    conditions of the day being predicted, not of the day it was fitted on.
    """
    out = []
    for i, d in enumerate(days):
        if d.day_class is DayClass.VALID_PRODUCING and d.q_24h is not None:
            out.append((i, d.q_24h, d.day.choke_size))
    return out


def backtest_well(
    well: str,
    days: Sequence[ClassifiedDay],
    windows: Sequence[StableWindow],
    model: ExpectationModel,
    *,
    horizons: Sequence[int] = HORIZONS,
) -> list[EvaluatedDay]:
    """Fit on each window and carry forward, collecting every evaluated day."""
    ordered = sorted(days, key=lambda d: d.day.production_date)
    sequence = _valid_rates(ordered)
    if not sequence:
        return []

    position = {index: n for n, (index, _, _) in enumerate(sequence)}
    results: list[EvaluatedDay] = []

    for window_index, window in enumerate(windows):
        in_window = [d for d in ordered if window.start <= d.day.production_date <= window.end]
        fitted = model.fit(in_window)
        if fitted is None:
            continue

        # Where the window ends in the well's valid-producing-day sequence.
        last_in_window = [
            i
            for i, d in enumerate(ordered)
            if d.day.production_date <= window.end and i in position
        ]
        if not last_in_window:
            continue
        start_rank = position[last_in_window[-1]]

        for horizon in horizons:
            for step in range(1, horizon + 1):
                rank = start_rank + step
                if rank >= len(sequence):
                    break
                _, actual, choke = sequence[rank]
                prediction = fitted.predict(step, choke=choke)
                results.append(
                    EvaluatedDay(
                        well=well,
                        horizon=horizon,
                        steps_ahead=step,
                        window_index=window_index,
                        actual=actual,
                        predicted=prediction.q_expected,
                        lower=prediction.lower,
                        upper=prediction.upper,
                    )
                )
    return results


def run_backtest(
    history_by_well: Mapping[str, Sequence[ClassifiedDay]],
    windows_by_well: Mapping[str, Sequence[StableWindow]],
    *,
    models: Sequence[ExpectationModel] = CANDIDATE_MODELS,
    horizons: Sequence[int] = HORIZONS,
) -> dict[str, ModelResult]:
    """Backtest every candidate across every well."""
    out: dict[str, ModelResult] = {}
    for model in models:
        evaluated: list[EvaluatedDay] = []
        for well, days in history_by_well.items():
            evaluated.extend(
                backtest_well(well, days, windows_by_well.get(well, []), model, horizons=horizons)
            )
        out[model.name] = ModelResult(model_name=model.name, evaluated=tuple(evaluated))
    return out


class ConditionOutcome(BaseModel):
    """One of section 8's three conditions, with what it measured."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    passed: bool
    evaluable: bool
    detail: str


def condition_1_relative_wape(
    candidate: ModelResult, baselines: Sequence[ModelResult], *, horizons: Sequence[int] = HORIZONS
) -> ConditionOutcome:
    """Pooled WAPE at least 10% lower, relatively, than the better baseline, at every horizon."""
    lines, passed = [], True
    for horizon in horizons:
        own = candidate.pooled_wape(horizon)
        rivals = [b.pooled_wape(horizon) for b in baselines]
        best = min([r for r in rivals if r is not None], default=None)
        if own is None or best is None:
            return ConditionOutcome(
                name="relative WAPE",
                passed=False,
                evaluable=False,
                detail=f"no evaluated days at horizon {horizon}",
            )
        improvement = (best - own) / best
        ok = improvement >= RELATIVE_WAPE_IMPROVEMENT
        passed = passed and ok
        lines.append(f"H={horizon}: {own:.4f} vs best baseline {best:.4f}, {improvement:+.1%}")
    return ConditionOutcome(
        name="relative WAPE", passed=passed, evaluable=True, detail="; ".join(lines)
    )


def condition_2_lower_tail(
    result: ModelResult,
    *,
    horizons: Sequence[int] = HORIZONS,
    producer_count: int | None = None,
) -> ConditionOutcome:
    """Per-well Clopper-Pearson containment of the lower-tail rate, at every horizon.

    Two things the first version of this got wrong, both of which the protocol is explicit
    about. The evaluability denominator is the field's oil producers, not the wells that happen
    to have an evaluated day: a model evaluated on two of six producers has not been checked on
    the field. And when fewer than half reach the qualifying count, section 8 does not say the
    condition is unevaluable; it says to pool across all evaluated well-days under the same
    bounds and label the result as pooled. Pooling is the weaker test, because a pooled rate can
    sit inside the bounds while one well runs at 0.03 and another at 0.25, so the per-well rates
    are reported beside it.
    """
    low, high = LOWER_TAIL_BOUNDS
    wells = result.wells()
    denominator = producer_count if producer_count is not None else len(wells)
    lines: list[str] = []
    passed = True
    qualifying_overall = 0

    for horizon in horizons:
        qualifying = 0
        for well in wells:
            rows = [e for e in result.for_well(well) if e.horizon == horizon]
            if len(rows) < CALIBRATION_MIN_DAYS:
                continue
            qualifying += 1
            k = sum(1 for r in rows if r.below_lower)
            lo, hi = clopper_pearson(k, len(rows))
            ok = lo >= low and hi <= high
            passed = passed and ok
            lines.append(
                f"H={horizon} {well}: {k}/{len(rows)}={k / len(rows):.3f} "
                f"CI [{lo:.3f},{hi:.3f}] {'ok' if ok else 'FAIL'}"
            )
        qualifying_overall = max(qualifying_overall, qualifying)

        if denominator and qualifying < denominator / 2:
            rows = [e for e in result.evaluated if e.horizon == horizon]
            if not rows:
                continue
            k = sum(1 for r in rows if r.below_lower)
            lo, hi = clopper_pearson(k, len(rows))
            ok = lo >= low and hi <= high
            passed = passed and ok
            lines.append(
                f"H={horizon} POOLED ({qualifying}/{denominator} producers reached "
                f"{CALIBRATION_MIN_DAYS} days): {k}/{len(rows)}={k / len(rows):.3f} "
                f"CI [{lo:.3f},{hi:.3f}] {'ok' if ok else 'FAIL'}"
            )

    return ConditionOutcome(
        name="lower-tail calibration",
        passed=passed and bool(lines),
        evaluable=bool(lines),
        detail="; ".join(lines) if lines else "no evaluated days",
    )


def condition_3_bias(
    result: ModelResult, *, horizons: Sequence[int] = HORIZONS
) -> ConditionOutcome:
    """Mean residual within 5% of the well's mean rate, at every horizon, with a drift test.

    Section 8 asks for two things here and the first version implemented one. The bound applies
    to the mean residual, not the median, because cumulative shortfall is a sum and a skewed
    residual distribution can sit at median zero while accumulating a standing bias. And drift
    is tested by splitting each evaluated window at its midpoint in valid producing days and
    requiring the same bound in both halves, which is checkable where an eyeball test is not.
    """
    lines: list[str] = []
    passed = True
    evaluated_any = False

    for horizon in horizons:
        for well in result.wells():
            rows = [e for e in result.for_well(well) if e.horizon == horizon]
            if len(rows) < BIAS_MIN_DAYS:
                continue
            evaluated_any = True
            mean_actual = mean(r.actual for r in rows)
            if mean_actual == 0.0:
                continue
            ratio = mean(r.residual for r in rows) / mean_actual
            ok = abs(ratio) <= BIAS_TOLERANCE
            passed = passed and ok
            lines.append(f"H={horizon} {well}: mean {ratio:+.1%} {'ok' if ok else 'FAIL'}")

            drift_failures = []
            for window_index in sorted({r.window_index for r in rows}):
                window_rows = sorted(
                    (r for r in rows if r.window_index == window_index),
                    key=lambda r: r.steps_ahead,
                )
                if len(window_rows) < 4:
                    continue
                midpoint = len(window_rows) // 2
                for label, half in (
                    ("first", window_rows[:midpoint]),
                    ("second", window_rows[midpoint:]),
                ):
                    half_actual = mean(r.actual for r in half)
                    if half_actual == 0.0:
                        continue
                    half_ratio = mean(r.residual for r in half) / half_actual
                    if abs(half_ratio) > BIAS_TOLERANCE:
                        drift_failures.append(f"w{window_index}/{label} {half_ratio:+.1%}")
            if drift_failures:
                passed = False
                lines.append(
                    f"H={horizon} {well}: drift FAIL in {len(drift_failures)} half-windows "
                    f"(e.g. {', '.join(drift_failures[:3])})"
                )

    return ConditionOutcome(
        name="per-well bias and drift",
        passed=passed and evaluated_any,
        evaluable=evaluated_any,
        detail="; ".join(lines) if lines else "no well reached the minimum day count",
    )
